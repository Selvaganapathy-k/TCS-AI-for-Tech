import re
import json
from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, END
from .llm import available, ask, json_from


class S(TypedDict, total=False):
    documents: list
    requirements: list
    conflicts: list
    plan: list
    warnings: list


def extract_node(s: S):
    docs = s.get("documents", [])
    reqs, warnings = [], []

    if available():
        prompt = (
            "Extract software requirements from the supplied sources. "
            "Return ONLY a valid JSON array. Each object must contain: "
            "type (Functional or NFR), category, statement, value, priority, "
            "source (filename), evidence (exact short phrase), confidence (0..1). "
            "Do not invent facts. Preserve every distinct requirement.\n\n"
            + "\n\n".join(
                "SOURCE: " + d["name"] + "\n" + d["text"][:12000]
                for d in docs
            )
        )
        try:
            data = json_from(ask(prompt))
            if isinstance(data, list):
                for i, item in enumerate(data, 1):
                    if isinstance(item, dict) and item.get("statement"):
                        item.setdefault("type", "Functional")
                        item.setdefault("category", "general")
                        item.setdefault("priority", "Medium")
                        item.setdefault("source", docs[0]["name"] if docs else "Unknown")
                        item.setdefault("evidence", item["statement"])
                        item.setdefault("confidence", 0.6)
                        item["id"] = f"REQ-{i:03d}"
                        reqs.append(item)
            else:
                warnings.append("Ollama extraction returned a non-array response.")
        except Exception as exc:
            warnings.append("Ollama extraction failed; deterministic fallback used: " + type(exc).__name__)
    else:
        warnings.append("Ollama unavailable; deterministic extraction used.")

    if not reqs:
        patterns = [
            ("scalability", r"[\d,]+\s*(?:concurrent users|users concurrently)"),
            ("availability", r"[\d.]+\s*%\s*(?:availability|uptime)"),
            ("security", r"encrypt(?:ion)?|MFA|TLS|PCI-compliant"),
            ("guest_checkout", r"guest checkout"),
        ]
        for doc in docs:
            for category, pattern in patterns:
                for match in re.finditer(pattern, doc.get("text", ""), re.I):
                    value = match.group(0)
                    reqs.append({
                        "id": f"REQ-{len(reqs)+1:03d}",
                        "type": "NFR" if category != "guest_checkout" else "Functional",
                        "category": category,
                        "statement": "The system must address " + value,
                        "value": value,
                        "priority": "High",
                        "source": doc.get("name", "Unknown"),
                        "evidence": value,
                        "confidence": 0.85,
                    })

    if not reqs and docs:
        reqs = [{
            "id": "REQ-001", "type": "Functional", "category": "core",
            "statement": "Support the core workflow described in the supplied evidence.",
            "value": "core workflow", "priority": "High",
            "source": docs[0].get("name", "Unknown"),
            "evidence": "Manual review required", "confidence": 0.3,
        }]

    return {"requirements": reqs, "warnings": warnings}


def conflict_node(s: S):
    groups = {}
    for req in s.get("requirements", []):
        category = str(req.get("category", "")).lower()
        numbers = re.findall(r"[\d,]+", str(req.get("value", req.get("statement", ""))))
        if numbers and category in ["scalability", "availability"]:
            groups.setdefault(category, []).append((req, numbers[0].replace(",", "")))

    conflicts = []
    for category, items in groups.items():
        if len({value for _, value in items}) > 1:
            conflicts.append({
                "id": f"CON-{len(conflicts)+1:03d}",
                "category": category,
                "severity": "High",
                "description": f"Conflicting {category} values appear in the supplied evidence. Please confirm the accepted value.",
                "evidence": [
                    {"requirement_id": req["id"], "source": req["source"], "value": value}
                    for req, value in items
                ],
                "status": "unresolved",
                "resolution": "",
            })

    for req in s.get("requirements", []):
        if float(req.get("confidence", 0.5)) < 0.5:
            conflicts.append({
                "id": f"CON-{len(conflicts)+1:03d}",
                "category": "ambiguity",
                "severity": "High",
                "description": "Please clarify: " + req["statement"],
                "evidence": [{
                    "requirement_id": req["id"],
                    "source": req.get("source", "Unknown"),
                    "value": req.get("evidence", ""),
                }],
                "status": "unresolved",
                "resolution": "",
            })

    # Ask the local LLM to identify questions that cannot safely be answered
    # from the supplied evidence. Existing high-severity conflicts remain.
    if available():
        evidence = {
            "requirements": s.get("requirements", []),
            "already_detected_conflicts": conflicts,
        }
        clarification_prompt = """
You are a senior requirements analyst and software architect.
Review the supplied requirements and source evidence. Identify stakeholder
questions that must be answered before a reliable architecture can be approved.

Consider these five categories:
1. ambiguity: vague terms, unclear scope or measurable targets.
2. missing_information: essential requirements or operational details absent.
3. contradiction: incompatible statements or values across sources.
4. assumption: an assumption the architect would otherwise have to make.
5. architectural_constraint: deployment, cloud/on-premises, budget, compliance,
   data residency, integrations, legacy systems, technology mandates, RTO/RPO,
   throughput, or other constraints that materially affect architecture.

Return ONLY a JSON array. Each item must have:
{
  "category": "one of the five categories",
  "question": "one clear question addressed to the stakeholder",
  "reason": "why the answer changes or validates the architecture",
  "evidence": "short source evidence or 'Not specified in supplied documents'",
  "options": ["3-5 concise choices relevant to this question, with 'Other' as the final choice"]
}

Rules:
- Ask only useful questions whose answers could change the requirements,
  architecture, technology choice, cost, security, reliability or deployment.
- Do not ask for information already clearly specified.
- For contradictions, state the competing values in the question.
- For assumptions, phrase the assumption as a confirmation question.
- Ask at most 8 questions, prioritizing architecture-blocking unknowns.
- Provide 3-5 relevant, mutually understandable choices for each question.
- Always include the exact final option "Other".
- Do not invent facts or treat an assumption as an approved decision.
""" + json.dumps(evidence, ensure_ascii=False)

        try:
            question_items = json_from(ask(
                clarification_prompt,
                system="You are a rigorous requirements clarification agent. Return valid JSON only."
            ))
            if isinstance(question_items, list):
                existing_descriptions = {
                    str(item.get("description", "")).strip().lower()
                    for item in conflicts
                }
                for item in question_items[:8]:
                    if not isinstance(item, dict) or not item.get("question"):
                        continue
                    question = str(item["question"]).strip()
                    if question.lower() in existing_descriptions:
                        continue
                    evidence_text = str(item.get("evidence", "Not specified in supplied documents"))
                    conflicts.append({
                        "id": f"CON-{len(conflicts)+1:03d}",
                        "category": str(item.get("category", "missing_information")),
                        "severity": "High",
                        "description": question,
                        "reason": str(item.get("reason", "")),
                        "evidence": [{
                            "requirement_id": "N/A",
                            "source": "AI clarification analysis",
                            "value": evidence_text,
                        }],
                        "status": "unresolved",
                        "resolution": "",
                        "options": (
                            [str(x).strip() for x in item.get("options", [])
                             if isinstance(x, (str, int, float)) and str(x).strip()
                             and str(x).strip().lower() != "other"][:4]
                            + ["Other"]
                        ),
                    })
        except Exception as exc:
            s.setdefault("warnings", []).append(
                "LLM clarification analysis failed: " + type(exc).__name__
            )

    defaults = {
        "scalability": ["Up to 1,000 users", "Up to 10,000 users", "More than 10,000 users"],
        "availability": ["99.0%", "99.9%", "99.99%"],
        "ambiguity": ["Use the requirement as written", "Ask the stakeholder to define it", "Record an explicit assumption"],
        "missing_information": ["Required for the first release", "Can be decided during detailed design", "Not required"],
        "contradiction": ["Use the first source value", "Use the second source value", "Reconcile with the stakeholder"],
        "architectural_constraint": ["Cloud", "On-premises", "Hybrid"],
        "assumption": ["Approve the proposed assumption", "Reject the assumption", "Defer the decision"],
    }
    for conflict in conflicts:
        choices = conflict.get("options") or defaults.get(
            str(conflict.get("category", "")).lower(), ["Yes", "No", "Not sure"]
        )
        choices = [str(choice).strip() for choice in choices
                   if str(choice).strip() and str(choice).strip().lower() != "other"]
        conflict["options"] = choices[:4] + ["Other"]

    return {"conflicts": conflicts}


def plan_node(s: S):
    has_conflicts = bool(s.get("conflicts"))
    return {"plan": [
        {"step": 1, "action": "Extract and normalize requirements with source evidence", "status": "completed"},
        {"step": 2, "action": "Detect contradictions and request stakeholder clarification",
         "status": "awaiting_human" if has_conflicts else "completed"},
        {"step": 3, "action": "Decompose requirements into architecture components",
         "status": "blocked" if has_conflicts else "pending"},
        {"step": 4, "action": "Generate APIs, data flows and architecture decisions",
         "status": "blocked" if has_conflicts else "pending"},
        {"step": 5, "action": "Verify traceability, risks and architecture consistency",
         "status": "blocked" if has_conflicts else "pending"},
    ]}


graph = StateGraph(S)
graph.add_node("extract", extract_node)
graph.add_node("detect_conflicts", conflict_node)
graph.add_node("create_plan", plan_node)
graph.set_entry_point("extract")
graph.add_edge("extract", "detect_conflicts")
graph.add_edge("detect_conflicts", "create_plan")
graph.add_edge("create_plan", END)
workflow = graph.compile()


def analyze(docs):
    return workflow.invoke({"documents": docs, "warnings": []})


def _fallback_architecture(requirements):
    """Requirement-informed fallback used only when Ollama is unavailable or returns invalid JSON."""
    text = " ".join(
        str(r.get("statement", "")) + " " + str(r.get("value", ""))
        for r in requirements
    ).lower()

    components = [
        {"name": "Web or Mobile Client", "responsibility": "User-facing application and request submission", "requirements": []},
        {"name": "API Gateway", "responsibility": "Request routing, authentication enforcement and rate limiting", "requirements": []},
        {"name": "Domain Services", "responsibility": "Core business workflows and application rules", "requirements": []},
        {"name": "Primary Database", "responsibility": "Durable transactional storage", "requirements": []},
    ]

    if any(k in text for k in ["payment", "checkout", "refund", "transaction"]):
        components.append({"name": "Payment Service", "responsibility": "Payment provider integration, idempotency and transaction status", "requirements": []})
    if any(k in text for k in ["seat", "inventory", "reservation", "lock"]):
        components.append({"name": "Inventory and Reservation Service", "responsibility": "Availability checks and time-bound resource reservation", "requirements": []})
    if any(k in text for k in ["search", "catalog", "filter"]):
        components.append({"name": "Search and Catalog Service", "responsibility": "Search, filtering and catalog queries", "requirements": []})
    if any(k in text for k in ["email", "sms", "notification", "notify"]):
        components.append({"name": "Notification Service", "responsibility": "Email, SMS and event notifications", "requirements": []})
    if any(k in text for k in ["real-time", "realtime", "within 1 second", "live update"]):
        components.append({"name": "Event Streaming / WebSocket Service", "responsibility": "Publish changes and push live updates to connected clients", "requirements": []})
    if any(k in text for k in ["100000", "100,000", "500000", "500,000", "million", "concurrent", "traffic spike", "horizontal scaling"]):
        components.extend([
            {"name": "Distributed Cache", "responsibility": "Low-latency reads, hot data and short-lived locks", "requirements": []},
            {"name": "Message Broker", "responsibility": "Asynchronous event processing and workload buffering", "requirements": []},
            {"name": "Load Balancer and Autoscaling", "responsibility": "Distribute traffic and scale service instances based on demand", "requirements": []},
        ])

    # Cross-cutting capabilities are deliberately not placed in the request chain.
    cross_cutting = []
    if any(k in text for k in ["encrypt", "security", "oauth", "jwt", "authentication", "pci"]):
        cross_cutting.append("Security: encryption, identity, authorization and secrets management")
    if any(k in text for k in ["audit", "monitor", "observability", "logs", "metrics", "traces", "99."]):
        cross_cutting.append("Observability: logs, metrics, traces, audit events and alerting")
    if not cross_cutting:
        cross_cutting.append("Observability: logs, metrics, traces and alerting")

    for req in requirements:
        category = str(req.get("category", "")).lower()
        statement = str(req.get("statement", "")).lower()
        target = 2
        if "payment" in category or "payment" in statement:
            target = next((i for i,c in enumerate(components) if c["name"] == "Payment Service"), 2)
        elif any(k in category + statement for k in ["seat", "inventory", "reservation"]):
            target = next((i for i,c in enumerate(components) if c["name"] == "Inventory and Reservation Service"), 2)
        elif any(k in category + statement for k in ["search", "catalog"]):
            target = next((i for i,c in enumerate(components) if c["name"] == "Search and Catalog Service"), 2)
        elif "security" in category:
            target = 1
        elif "database" in category or "data" in category:
            target = 3
        components[target]["requirements"].append(req.get("id", ""))

    edges = []
    names = [c["name"] for c in components]
    for left, right in zip(names, names[1:]):
        edges.append({"from": left, "to": right, "label": "request / response"})
    if "Message Broker" in names:
        for name in names:
            if name not in ["Message Broker", "Web or Mobile Client", "API Gateway", "Primary Database", "Distributed Cache", "Load Balancer and Autoscaling"]:
                edges.append({"from": name, "to": "Message Broker", "label": "domain event"})
    if "Distributed Cache" in names:
        edges.append({"from": "API Gateway", "to": "Distributed Cache", "label": "cache lookup"})
        edges.append({"from": "Distributed Cache", "to": "Primary Database", "label": "cache miss"})
    return {
        "pattern": "Requirement-driven modular service architecture",
        "components": components,
        "connections": edges,
        "cross_cutting_concerns": cross_cutting,
        "diagram": "",
        "apis": [
            {"method": "GET", "path": "/api/v1/health", "purpose": "Health check"},
            {"method": "POST", "path": "/api/v1/requests", "purpose": "Submit the primary business request"},
        ],
        "data_flow": ["Client submits a request", "Gateway validates and routes the request", "Relevant domain service applies business rules", "Database persists the transaction", "Events are published for asynchronous processing where required"],
        "assumptions": ["Detailed throughput, latency and recovery objectives require stakeholder confirmation"],
        "risks": ["Database contention under peak load", "External service failures require timeout, retry and idempotency controls"],
        "adr": [{
            "id": "ADR-001", "title": "Use a modular service architecture",
            "decision": "Separate edge routing, domain logic and persistence.",
            "reason": "Keeps responsibilities clear and allows later scaling based on measured demand.",
            "status": "Proposed",
        }],
    }


def _make_mermaid(architecture):
    components = architecture.get("components", [])
    connections = architecture.get("connections", [])
    lines = ["flowchart LR"]
    ids = {}
    for index, component in enumerate(components):
        node_id = f"C{index}"
        ids[component["name"]] = node_id
        safe_name = str(component["name"]).replace('"', "'")
        lines.append(f'  {node_id}["{safe_name}"]')
    for edge in connections:
        source, target = edge.get("from"), edge.get("to")
        if source in ids and target in ids:
            label = str(edge.get("label", "")).replace('"', "'")
            lines.append(f'  {ids[source]} -->|"{label}"| {ids[target]}')
    if architecture.get("cross_cutting_concerns"):
        lines.append('  X["Cross-cutting: ' + "; ".join(architecture["cross_cutting_concerns"]).replace('"', "'") + '"]')
        for node_id in ids.values():
            lines.append(f"  X -.-> {node_id}")
    return "\n".join(lines)


def design(state):
    requirements = state.get("requirements", [])
    conflicts = state.get("conflicts", [])
    unresolved_high = [
        c for c in conflicts
        if c.get("severity") == "High" and c.get("status") != "resolved"
    ]

    architecture = None
    generation_mode = "ollama"
    if available():
        prompt_data = {
            "requirements": requirements,
            "resolved_conflicts": [c for c in conflicts if c.get("status") == "resolved"],
            "unresolved_conflicts": unresolved_high,
        }
        prompt = """
You are ArchIntel AI, a senior software architect. Design an architecture from the supplied evidence.
Do not return a generic template. Every component, connection, API and decision must be justified by the actual requirements.
Do not silently choose between unresolved high-severity conflicts. State assumptions and mark the architecture as provisional if conflicts remain.
Return ONLY valid JSON with this exact top-level shape:
{
  "pattern": "architecture pattern and short rationale",
  "components": [{"name":"...", "responsibility":"...", "requirements":["REQ-001"]}],
  "connections": [{"from":"component name","to":"component name","label":"purpose"}],
  "cross_cutting_concerns": ["security / observability / resilience concerns; not sequential request-flow nodes"],
  "apis": [{"method":"GET|POST|PUT|PATCH|DELETE","path":"/api/...","purpose":"..."}],
  "data_flow": ["ordered meaningful data-flow steps"],
  "assumptions": ["explicit assumptions"],
  "risks": ["technical risks and mitigations"],
  "adr": [{"id":"ADR-001","title":"...","decision":"...","reason":"...","status":"Proposed"}]
}
Rules:
- Use only relevant components; do not add Redis, Kafka, microservices or Kubernetes unless evidence justifies them.
- Include requirement IDs in component mappings. Do not invent requirement IDs.
- Represent asynchronous messaging as event connections, not as a mandatory step after the database.
- Represent monitoring, security and audit as cross-cutting concerns, not as a sequential business component.
- For concurrency, availability, latency and consistency requirements, explain the mechanisms and trade-offs.
- Include payment idempotency, transactional safeguards or equivalent controls when payment/booking requirements need them.
- Keep component and connection names consistent.
Input evidence:
""" + json.dumps(prompt_data, ensure_ascii=False)
        try:
            candidate = json_from(ask(
                prompt,
                system="You are ArchIntel AI, a precise software architecture agent. Return valid JSON only. Do not use markdown fences."
            ))
            if isinstance(candidate, dict) and isinstance(candidate.get("components"), list) and candidate["components"]:
                architecture = candidate
            else:
                state.setdefault("warnings", []).append("Ollama architecture response did not match the required JSON schema.")
        except Exception as exc:
            state.setdefault("warnings", []).append("Ollama architecture generation failed; requirement-informed fallback used: " + type(exc).__name__)
    else:
        state.setdefault("warnings", []).append("Ollama is unavailable during architecture generation; requirement-informed fallback used.")

    if architecture is None:
        generation_mode = "requirement-informed-fallback"
        architecture = _fallback_architecture(requirements)

    valid_ids = {r.get("id") for r in requirements}
    components = architecture.get("components", [])
    for component in components:
        component.setdefault("name", "Unnamed component")
        component.setdefault("responsibility", "Responsibility requires review")
        component["requirements"] = [
            rid for rid in component.get("requirements", [])
            if rid in valid_ids
        ]

    architecture.setdefault("connections", [])
    architecture.setdefault("cross_cutting_concerns", [])
    architecture.setdefault("apis", [])
    architecture.setdefault("data_flow", [])
    architecture.setdefault("assumptions", [])
    architecture.setdefault("risks", [])
    architecture.setdefault("adr", [])
    architecture["diagram"] = _make_mermaid(architecture)
    architecture["generation_mode"] = generation_mode
    architecture["provisional"] = bool(unresolved_high)

    mapped = {rid for component in components for rid in component.get("requirements", [])}
    requirement_ids = {r.get("id") for r in requirements}
    coverage = round(len(mapped & requirement_ids) / len(requirement_ids) * 100, 1) if requirement_ids else 0
    checks = [
        {"name": "Requirement traceability", "passed": coverage >= 70,
         "detail": f"{len(mapped & requirement_ids)} of {len(requirement_ids)} requirements mapped ({coverage}%)."},
        {"name": "Architecture decomposition", "passed": len(components) >= 4,
         "detail": f"{len(components)} components proposed."},
        {"name": "API contracts", "passed": len(architecture["apis"]) > 0,
         "detail": f"{len(architecture['apis'])} API recommendations."},
        {"name": "Risk assessment", "passed": len(architecture["risks"]) > 0,
         "detail": f"{len(architecture['risks'])} risks documented."},
        {"name": "High-severity conflicts resolved", "passed": not unresolved_high,
         "detail": "Unresolved high-severity conflicts block sign-off."},
    ]
    verification = {
        "checks": checks,
        "passed": sum(check["passed"] for check in checks),
        "total": len(checks),
        "score": round(sum(check["passed"] for check in checks) / len(checks) * 100),
        "requirement_coverage": coverage,
        "traceability": [
            {
                "requirement_id": req.get("id"),
                "statement": req.get("statement", ""),
                "source": req.get("source", ""),
                "component": next(
                    (component["name"] for component in components
                     if req.get("id") in component.get("requirements", [])),
                    "UNMAPPED",
                ),
            }
            for req in requirements
        ],
    }
    return architecture, verification


def resolve(state, resolutions):
    for conflict in state.get("conflicts", []):
        if conflict["id"] in resolutions:
            conflict["resolution"] = resolutions[conflict["id"]]
            conflict["status"] = "resolved"
    state.setdefault("human_decisions", []).extend([
        {"conflict_id": key, "decision": value, "approved_by": "human"}
        for key, value in resolutions.items()
    ])
    return state


def change_requirement(state, text):
    match = re.search(r"([\d,]+)\s*(?:concurrent\s+users|users\s+concurrently)", text, re.I)
    if match:
        value = match.group(1)
        found = False
        for req in state.get("requirements", []):
            if req.get("category") == "scalability":
                req.update(
                    statement=f"The system must support {value} concurrent users.",
                    value=f"{value} concurrent users",
                    source="Jury change request",
                    evidence=text,
                    confidence=1.0,
                )
                found = True
        if not found:
            state.setdefault("requirements", []).append({
                "id": f"REQ-{len(state.get('requirements', []))+1:03d}",
                "type": "NFR", "category": "scalability",
                "statement": f"The system must support {value} concurrent users.",
                "value": f"{value} concurrent users", "priority": "High",
                "source": "Jury change request", "evidence": text, "confidence": 1.0,
            })
    state.setdefault("change_history", []).append({
        "change": text,
        "status": "approved",
        "affected_components": ["API Gateway", "Domain Services", "Database", "Cache", "Autoscaling"],
    })
    return state
