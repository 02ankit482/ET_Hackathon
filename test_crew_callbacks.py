# Test if CrewAI actually calls callbacks
import asyncio
import logging
from crewai import Agent, Task, Crew, Process, LLM
from config import CHAT_LLM, OPENROUTER_API_KEY, OPENAI_API_BASE

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Track callback invocations
callback_count = 0

def my_step_callback(step_output):
    global callback_count
    callback_count += 1
    logger.info(f"✓ step_callback called #{callback_count}: {type(step_output)}")
    logger.info(f"  Content: {str(step_output)[:100]}")

def my_task_callback(task_output):
    global callback_count  
    callback_count += 1
    logger.info(f"✓ task_callback called #{callback_count}: {type(task_output)}")
    logger.info(f"  Content: {str(task_output)[:100]}")

async def test_crew():
    llm = LLM(
        model=CHAT_LLM,
        base_url=OPENAI_API_BASE,
        api_key=OPENROUTER_API_KEY,
        temperature=0.7,
        max_tokens=500,
    )
    
    agent = Agent(
        role="Test Agent",
        goal="Answer a simple question",
        backstory="A helpful test agent",
        llm=llm,
        verbose=True
    )
    
    task = Task(
        description="What is 2+2?",
        expected_output="The number 4",
        agent=agent
    )
    
    logger.info("Creating crew with callbacks...")
    crew = Crew(
        agents=[agent],
        tasks=[task],
        process=Process.sequential,
        verbose=True,
        step_callback=my_step_callback,
        task_callback=my_task_callback,
    )
    
    logger.info("Starting crew kickoff...")
    result = await crew.kickoff_async()
    logger.info(f"Crew completed. Result: {result}")
    logger.info(f"Total callbacks invoked: {callback_count}")

if __name__ == "__main__":
    asyncio.run(test_crew())
