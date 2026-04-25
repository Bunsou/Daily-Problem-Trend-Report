from google import genai
from config import GEMINI_API_KEY

# Create a client — this is the new pattern
client = genai.Client(api_key=GEMINI_API_KEY)

# Send a simple test prompt
response = client.models.generate_content(
    model="gemini-2.5-flash-lite",
    contents="Say hello in one short sentence.",
)

print(response.text)