from google import genai
import os
os.environ.setdefault('GOOGLE_GENAI_USE_VERTEXAI', 'TRUE')
os.environ.setdefault('GOOGLE_CLOUD_PROJECT', 'your-gcp-project-id')
#os.environ.setdefault('GOOGLE_CLOUD_LOCATION', 'northamerica-northeast1')
os.environ.setdefault('GOOGLE_CLOUD_LOCATION', 'global')
client = genai.Client()

# Use the -preview suffix for 3.x series
models_to_test = [
    'gemini-2.5-flash', 
    'gemini-2.5-pro', 
    'gemini-3.1-flash-preview', 
    'gemini-3.1-pro-preview',
    'gemini-3.1-flash-lite-preview'
]

for model in models_to_test:
    try:
        r = client.models.generate_content(model=model, contents='hi')
        print(f'{model}: OK')
    except Exception as e:
        print(f'{model}: {str(e)[:100]}')

# List all models available to your specific Vertex AI location
for model in client.models.list():
    if 'gemini-3.1' in model.name:
        print(f"Available ID: {model.name}")