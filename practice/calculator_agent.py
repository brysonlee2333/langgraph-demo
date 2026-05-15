from langchain.tools import tool
import os

from langchain_core.messages import HumanMessage

import config_data as config
from langchain.chat_models import init_chat_model
from dotenv import load_dotenv
from typing_extensions import TypedDict, Annotated
from typing import Literal
from langchain.messages import AnyMessage, SystemMessage, ToolMessage
from langgraph.graph import StateGraph, START, END
from IPython.display import Image, display
import operator

load_dotenv()
model = init_chat_model(
    model=config.chat_model_name,
    model_provider=config.chat_model_provider,
    base_url=os.getenv("DASHSCOPE_BASE_URL"),
    api_key=os.getenv("DASHSCOPE_API_KEY")
)

# Define tools
@tool
def multiply(a: int, b: int) -> int:
    """
    Multiplies 'a' and 'b'
    :param a:  first number
    :param b: second number
    :return:
    """
    return a * b

@tool
def add(a: int, b: int) -> int:
    """
    Adds 'a' and 'b'
    :param a: first int
    :param b: second int
    :return:
    """
    return a + b

@tool
def divide(a: int, b: int) -> float:
    """
    Divides 'a' and 'b'
    :param a: first int
    :param b: second int
    :return:
    """
    return a / b

# Augment the LLM with tools
tools = [
    multiply,
    add,
    divide
]

tools_by_name = {tool.name: tool for tool in tools}
model_with_tools = model.bind_tools(tools)

# 图状态用来存储信息和LLM的调用次数
class MessagesState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    llm_call: int

# 模型节点用于调用大模型，决定是否调用工具
def llm_call(state: dict):
    """LLM decides whether to call a tool or not"""
    result = {
        "messages": [
            model_with_tools.invoke(
                [
                    SystemMessage(
                        content="You are a helpful assistant tasked with performing arithmetic on a set of inputs."
                    )
                ]
                + state["messages"]
            )
        ],
        "llm_call": state.get("llm_call", 0) + 1
    }
    print(result)
    # 结点函数return的内容会被合并到state中，相同的key则覆盖，不同的则追加
    return result


# 工具节点用于调用工具并返回结果
def tool_node(state: dict):
    """ Performs the tool call"""
    result = []
    for tool_call in state["messages"][-1].tool_calls:
        tool = tools_by_name[tool_call["name"]]
        observation = tool.invoke(tool_call["args"])
        # 工具调用的id和对应的执行结果需要一一对应，放入到工具消息列表中
        result.append(ToolMessage(content=observation, tool_call_id=tool_call["id"]))
        return {"messages": result}

def should_continue(state: MessagesState) -> Literal["tool_node", END]:
    """decide if we should continue the loop or stop based upon whether the LLM made a tool call"""
    messages = state["messages"]
    last_message = messages[-1]

    # if the LLM makes a tool call, then perform an action
    if last_message.tool_calls:
        return "tool_node"
    # otherwise, we stop
    return END

# build workflow
agent_builder = StateGraph(MessagesState)

# add nodes
agent_builder.add_node("llm_call", llm_call)
agent_builder.add_node("tool_node", tool_node)

# add edges to connect nodes
agent_builder.add_edge(START, "llm_call")
# source 源节点 path：路径判断业务逻辑 path_map: 可能进入的分支节点列表
agent_builder.add_conditional_edges(
    "llm_call",
    should_continue,
    ["tool_node", END]
)

agent_builder.add_edge("tool_node", "llm_call")

# compile the agent
agent = agent_builder.compile()

display(Image(agent.get_graph(xray=True).draw_mermaid_png()))

#invoke
messages = [HumanMessage(content="add 3 and 4")]
messages = agent.invoke({"messages": messages})
for m in messages["messages"]:
    m.pretty_print()