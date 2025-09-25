import os
from jinja2 import Environment, FileSystemLoader
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage

PROMPT_FILE = os.path.join(os.path.dirname(__file__), "..", "prompts", "material_agent.jinja2")

def get_prompt(context=None):
    env = Environment(loader=FileSystemLoader(os.path.dirname(PROMPT_FILE)))
    template = env.get_template("material_agent.jinja2")
    return template.render(context=context)

class MaterialAgent:
    name = "material_agent"

    def __init__(self, context=None):
        self.system_prompt = get_prompt(context)
        self.llm = ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL") or None,
            temperature=float(os.getenv("OPENAI_TEMPERATURE", "0")),
            streaming=True,
        )

    def invoke(self, state):
        messages = [SystemMessage(content=self.system_prompt)] + state["messages"]
        return {"messages": self.llm.invoke(messages)}

def get_material_agent(context=None):
    return MaterialAgent(context)
