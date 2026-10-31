import os
import certifi
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

uri = os.getenv("MONGODB_URI")

client = MongoClient(
    uri,
    tls=True,
    tlsCAFile=certifi.where(),
    serverSelectionTimeoutMS=15000
)

try:
    print(client.admin.command("ping"))
    print("MongoDB Atlas connected successfully!")
except Exception as e:
    print(type(e).__name__, e)
finally:
    client.close()