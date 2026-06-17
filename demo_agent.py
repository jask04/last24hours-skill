import asyncio
import sys
from pathlib import Path
try:
    from google.antigravity import Agent, LocalAgentConfig
except ImportError:
    print("Error: The 'google.antigravity' module is not installed.")
    print("Please install it using: pip install google-antigravity")
    sys.exit(1)

# Import our custom tool
sys.path.insert(0, str(Path(__file__).parent / "scripts"))
from antigravity_tool import forecast_last_24_hours

async def main():
    # Configure the agent to load skills from the current directory
    # and provide the explicit custom Python tool.
    config = LocalAgentConfig(
        skills_paths=[str(Path(__file__).parent)],
        tools=[forecast_last_24_hours],
    )
    
    # Initialize the agent
    print("Starting Antigravity agent...")
    async with Agent(config) as agent:
        # Give the agent a prompt to test the forecasting tool
        prompt = "Using your forecast tool, what are the NBA games tomorrow? Show me the market picks."
        print(f"User: {prompt}\n")
        print("Agent:")
        
        response = await agent.chat(prompt)
        
        # Stream the agent's response
        async for chunk in response:
            print(chunk, end="", flush=True)
        print()

if __name__ == "__main__":
    asyncio.run(main())
