#!/usr/bin/env python3
"""
Example script demonstrating the AH Shopping Agent usage.
"""
import asyncio
from shopping_agent import AHShoppingAgent
from config import AgentConfig

async def main():
    """Run a simple example of the shopping agent."""
    
    print("🛍️ AH Shopping Agent Example")
    print("=" * 50)
    
    # Option 1: Use default configuration
    print("Using default configuration...")
    agent = AHShoppingAgent()
    
    # Option 2: Use custom configuration
    # config = AgentConfig(
    #     llm_provider="ollama",
    #     model_name="llama3.2",
    #     meat_count=2,
    #     vegetable_count=4,
    #     fruit_count=2,
    #     headless_automation=False  # Show browser during automation
    # )
    # agent = AHShoppingAgent(config=config)
    
    # Option 3: Use environment configuration
    # config = AgentConfig.from_env()
    # agent = AHShoppingAgent(config=config)
    
    try:
        # Run the complete workflow
        result = await agent.run_shopping_workflow()
        print("\n🎉 Shopping workflow completed successfully!")
        
    except Exception as e:
        print(f"❌ Error running shopping workflow: {e}")
        print("Make sure you have:")
        print("- Ollama running with llama3.2 model (or OpenAI API key set)")
        print("- Chrome browser installed")
        print("- Stable internet connection")

if __name__ == "__main__":
    asyncio.run(main())