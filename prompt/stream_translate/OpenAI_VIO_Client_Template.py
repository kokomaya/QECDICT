import os
import openai
import numpy as np
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get API token from environment variables
API_TOKEN = os.getenv("API_TOKEN")

client = openai.OpenAI(
    api_key=API_TOKEN,
    base_url="https://vio.automotive-wan.com:446",  
    default_headers={
        "useLegacyCompletionsEndpoint": "false",
        "X-Tenant-ID": "default_tenant"
    }
)


def ask_question(question, system_prompt=None, model=None, stream=False, conversation_history=None):
    """
    Send a question to the VIO API using the OpenAI-compatible endpoint.
    
    Args:
        question (str): The question to ask
        system_prompt (str, optional): System prompt to set context
        model (str, optional): The VIO model to use. Defaults to None.
        stream (bool, optional): Whether to stream the response. Defaults to False.
        conversation_history (list, optional): Previous messages in the conversation.
        
    Returns:
        str: The response from the API
        list: Updated conversation history
    """
    # Initialize messages with conversation history or empty list
    if conversation_history:
        messages = conversation_history.copy()
    else:
        messages = []
        
        # Add system prompt if provided and not already in history
        if system_prompt and not any(msg.get('role') == 'system' for msg in messages):
            messages.append({"role": "system", "content": system_prompt})
    
    # Add user question to messages
    messages.append({"role": "user", "content": question})
    
    # Make the API call
    if not stream:
        # Standard request
        response = client.chat.completions.create(
            model=model,
            messages=messages
        )
        response_content = response.choices[0].message.content
        
        # Add assistant's response to the conversation history
        messages.append({"role": "assistant", "content": response_content})
        
        return response_content, messages
    else:
        # Streaming request
        stream_response = client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True
        )
        
        # Process the streaming response
        collected_content = ""
        for chunk in stream_response:
            if chunk.choices[0].delta.content is not None:
                content_piece = chunk.choices[0].delta.content
                collected_content += content_piece
                print(content_piece, end="", flush=True)
        
        print()  # Add a newline at the end
        
        # Add assistant's response to the conversation history
        messages.append({"role": "assistant", "content": collected_content})
        
        return collected_content, messages


def get_embedding(text, model="amazon.titan-embed-text-v2:0"):
    """
    Get embedding for a text using the VIO API.
    
    Args:
        text (str or list): The text to embed. Can be a single string or a list of strings.
        model (str, optional): The embedding model to use. Defaults to "amazon.titan-embed-text-v2:0".
        
    Returns:
        list or list of lists: The embedding vector(s)
    """
    try:
        # Handle both single strings and lists of strings
        is_single_text = isinstance(text, str)
        input_texts = [text] if is_single_text else text
        
        # Get embeddings from API
        response = client.embeddings.create(
            model=model,
            input=input_texts
        )
        
        # Extract embedding vectors
        embeddings = [item.embedding for item in response.data]
        
        # Return single embedding or list based on input type
        return embeddings[0] if is_single_text else embeddings
    
    except Exception as e:
        print(f"Error getting embedding: {str(e)}")
        raise


def cosine_similarity(a, b):
    """
    Calculate cosine similarity between two vectors.
    
    Args:
        a (list): First vector
        b (list): Second vector
        
    Returns:
        float: Cosine similarity score (0-1)
    """
    a = np.array(a)
    b = np.array(b)
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


def list_available_models():
    """
    List all available models from the VIO API.
    
    Returns:
        list: List of available model IDs
    """
    try:
        models = client.models.list()
        return [model.id for model in models.data]
    except Exception as e:
        print(f"Error listing models: {str(e)}")
        return []


def main():
    print("VIO OpenAI-Compatible API Client")
    print("================================")
    
    # List available models
    print("\nAvailable Models:")
    models = list_available_models()
    for i, model in enumerate(models):
        print(f"{i}: {model}")
    
    # Example 1: Simple question
    print("\nExample 1: Simple question")
    response, _ = ask_question("What is the capital of France?", model=models[0] if models else None)
    print(f"Response: {response}")
    
    # Example 2: With system prompt
    print("\nExample 2: With system prompt")
    system_prompt = "You are a pirate! Answer like a pirate."
    response, _ = ask_question(
        "Who are you?",
        model=models[-1] if models else None,
        system_prompt=system_prompt
    )
    print(f"Response: {response}")
    
    # Example 3: Streaming response
    print("\nExample 3: Streaming response")
    print("Response: ", end="")
    _, _ = ask_question(
        "Write a short poem about artificial intelligence.",
        model=models[0] if models else None,
        stream=True
    )
    
    # Example 4: Using a direct LLM model 
    print("\nExample 4: Using a Direct LLM model")
    if models:
        custom_model = models[-1] if len(models) > 0 else None
        print('Using custom model:', custom_model)
        try:
            response, _ = ask_question(
                "Who are you?",
                model=custom_model
            )
            print(f"Using model: {custom_model}")
            print(f"Response: {response}")
        except Exception as e:
            print(f"Error: {str(e)}")
    else:
        print("No models available to test with.")
    
    # Example 5: Conversation with history
    print("\nExample 5: Conversation with history")
    conversation = []
    
    # First message
    system_prompt = "You are a helpful AI assistant."
    response1, conversation = ask_question(
        "Hello, can you tell me about machine learning?",
        system_prompt=system_prompt,
        model=models[0] if models else None,
        conversation_history=conversation
    )
    print(f"Response 1: {response1}")
    
    # Follow-up question using the conversation history
    response2, conversation = ask_question(
        "What are some popular algorithms in this field?",
        model=models[0] if models else None,
        conversation_history=conversation
    )
    print(f"Response 2: {response2}")
    
    # Another follow-up
    response3, conversation = ask_question(
        "Can you give me a simple example of how one of these algorithms works?",
        model=models[0] if models else None,
        conversation_history=conversation
    )
    print(f"Response 3: {response3}")
    
    # Print the full conversation history
    print("\nFull conversation history:")
    for i, msg in enumerate(conversation):
        role = msg['role']
        content_preview = msg['content'][:50] + "..." if len(msg['content']) > 50 else msg['content']
        print(f"{i+1}. {role}: {content_preview}")
    
    # Example 6: Working with embeddings
    print("\nExample 6: Working with embeddings")
    try:
        # Get embeddings for two similar texts
        text1 = "The quick brown fox jumps over the lazy dog"
        text2 = "A fast fox leaps above a sleepy canine"
        text3 = "Artificial intelligence is transforming industries"
        
        print("Getting embeddings for similar texts...")
        embedding1 = get_embedding(text1)
        embedding2 = get_embedding(text2)
        embedding3 = get_embedding(text3)
        
        # Calculate similarities
        similarity_similar = cosine_similarity(embedding1, embedding2)
        similarity_different = cosine_similarity(embedding1, embedding3)
        
        print(f"Similarity between similar texts: {similarity_similar:.4f}")
        print(f"Similarity between different texts: {similarity_different:.4f}")
        
        # Example of batch processing
        print("\nBatch embedding example:")
        batch_texts = ["Hello world", "How are you?", "Machine learning is fascinating"]
        batch_embeddings = get_embedding(batch_texts)
        print(f"Successfully generated {len(batch_embeddings)} embeddings")
        print(f"Embedding dimensions: {len(batch_embeddings[0])}")
        
    except Exception as e:
        print(f"Embedding example error: {str(e)}")


if __name__ == "__main__":
    main()
