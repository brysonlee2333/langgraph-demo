"""
1.阅读用户邮件，自动跟踪回复
2.用户邮件主要有三种意图： 文档搜索、bug追踪、人工检视

需要在state中存储的内容：邮件原文（邮件正文、发件人信息）
"""
import os
from typing import TypedDict, Literal
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage
from langchain_core.prompts import PromptTemplate
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel, Field

import config_data as config
from dotenv import load_dotenv
from langgraph.types import interrupt, Command, RetryPolicy
from langgraph.graph import START, END, StateGraph

# define the structure for email classification
class EmailClassification(BaseModel):
    intent: Literal["question", "bug", "billing", "feature", "complex"]
    urgency: Literal["low", "medium", "high", "critical"]
    topic: str
    summary: str

class EmailAgentState(TypedDict):
    # Raw email data
    email_content: str
    sender_email: str
    email_id: str

    # Classification result
    classification: EmailClassification | None

    # Raw search/API result
    search_results: list[str] | None #原始文档片段
    customer_history: dict | None #从CRM系统获取的原始客户信息

    # Generated content
    draft_response: str | None
    messages: list[str] | None

load_dotenv()
llm = init_chat_model(
    model=config.chat_model_name,
    model_provider=config.chat_model_provider,
    base_url = os.getenv("DASHSCOPE_BASE_URL"),
    api_key = os.getenv("DASHSCOPE_API_KEY"),
    temperature=0.0,  # 🔥 必须 0
)

def read_email(state: EmailAgentState) -> dict:
    """extract and parse email content"""
    # in production, this would connect to your email service
    return {
        "messages": [HumanMessage(content=f"处理邮件内容: {state['email_content']}")]
    }

def classify_intent(state: EmailAgentState) -> Command[Literal["search_documentation", "human_review", "draft_response", "bug_tracking"]]:
    """use LLM to classify email intent and urgency, then route accordingly"""
    # 不是所有模型都支持结构化输出，不同模型的调用方式略有不同
    # format the prompt on-demand, not stored in state
    classification_prompt = """
    分析这封用户邮件，然后根据内容进行分类，只输出纯净JSON:
    
    Email:{email_content}
    From:{sender_email}
    
    供分类的有如下几个项目 intent（只能为"question", "bug", "billing", "feature", "complex"，不许随意编造）, urgency, topic, and summary. """
    structured_llm = llm.with_structured_output(EmailClassification, method="json_mode")
    prompt_template = PromptTemplate(
        template=classification_prompt,
        input_variables=["email_content", "sender_email"]
    )

    # get structured response directly as dict。
    # chain = prompt_template | llm | parser
    # classification = chain.invoke(state)
    prompt_value = prompt_template.invoke(state)
    print("模版拼接结果")
    print(prompt_value)

    classification = structured_llm.invoke(prompt_value)
    print("模型执行结果")
    print(classification)

    # determine next node based on classification
    if classification.intent == 'billing' or classification.urgency == 'critical':
        goto = "human_review"
    elif classification.intent in ['question', 'feature']:
        goto = "search_documentation"
    elif classification.intent == 'bug':
        goto = 'bug_tracking'
    else:
        goto = "draft_response"

    # store classification as a single dict in state
    return Command(
        update={"classification": classification},
        goto=goto
    )

class SearchAPIError(Exception):
    """自定义：搜索API调用失败"""
    pass

def search_documentation(state: EmailAgentState) -> Command[Literal["draft_response"]]:
    """search knowledge base for relevant information"""
    classification = state.get('classification',{})
    query = f"{classification.get('intent','')} {classification.get('topic', '')}"
    try:
        search_result = [
            "Reset password via setting > Security > Change Password",
            "Password must be at least 12 characters",
            "Include uppercase, lowercase, numbers, and symbols"
        ]
    except SearchAPIError as e:
        search_result = [f"Search temporarily unavailable: {str(e)}"]

    return Command(
        update={"search_result": search_result},
        goto="draft_response"
    )

def bug_tracking(state: EmailAgentState) -> Command[Literal["draft_response"]]:
    """ Create or update bug tracking ticket"""
    ticket_id = "BUG-1234" # would be create via API
    return Command(
        update={"search_results": [f"Bug ticket {ticket_id} created"],
                "current_step": "bug_tracked"},
        goto="draft_response"
    )

def draft_response(state: EmailAgentState) -> Command[Literal["human_review", "send_reply"]]:
    """generate response using context and route based on quality"""
    classification = state.get('classification',{})

    # format context from raw state data on-demand
    context_sections = []

    if state.get('search_results'):
        formatted_docs = "\n".join([f"- {doc}" for doc in state['search_results']])
        context_sections.append(f"Relevant documentation:\n{formatted_docs}")

    if state.get('customer_history'):
        # Format search result for prompt
        context_sections.append(f"Customer tier: {state['customer_history'].get('tier', 'standard')}")

    # build the prompt with formatted context
    draft_prompt = f"""
    Draft a response to this customer email:
    {state['email_content']}
    
    Email intent: {classification.get('intent', 'unknown')}
    Urgency level: {classification.get('urgency', 'medium')}
    {chr(10).join(context_sections)}

    Guidelines:
    - Be professional and helpful
    - Address their specific concern
    - Use the provided documentation when relevant"""

    response = llm.invoke(draft_prompt)

    # determine if human review needed based on urgency and intent
    need_review = (
        classification.get('urgency') in ['high', 'critical'] or
        classification.get('intent') == 'complex'
    )

    # route to appropriate next node
    goto = "human_review" if need_review else "send_reply"
    return Command(
        update={"draft_response": response.content}, # store only the raw response
        goto=goto
    )

def human_review(state: EmailAgentState) -> Command[Literal["send_reply", END]]:
    """Pause for human review using interrupt and route based on decision"""
    classification = state.get('classification',{})

    # interrupt() must come first - any code before it will re-run on resume
    human_decision = interrupt({
        "email_id": state.get('email_id', ''),
        "original_email": state.get('email_content', ''),
        "draft_response": state.get('draft_response', ''),
        "urgency": classification.urgency,
        "intent": classification.intent,
        "action": "Please review and approve/edit this response"
    })

    # now process the human's decision
    if human_decision.get("approved"):
        return Command(
            update={"draft_response": human_decision.get("edited_response", state.get('draft_response'))},
            goto="send_reply"
        )
    else:
        # rejection means human will handle directly
        return Command(update={}, goto=END)

def send_reply(state: EmailAgentState) -> dict:
    """send the email response"""
    # integrate with email service
    print(f"Sending reply:{state['draft_response'][:100]}...")
    return {}

# create the graph

workflow = StateGraph(EmailAgentState)

# add nodes with appropriate error handling
workflow.add_node("read_email", read_email)
workflow.add_node("classify_intent", classify_intent)

# add retry policy for nodes that might have transient failures
workflow.add_node(
    "search_documentation",
    search_documentation,
    retry_policy=RetryPolicy(max_attempts=3)
)
workflow.add_node("bug_tracking", bug_tracking)
workflow.add_node("draft_response", draft_response)
workflow.add_node("human_review", human_review)
workflow.add_node("send_reply", send_reply)

workflow.add_edge(START, "read_email")
workflow.add_edge("read_email", "classify_intent")
workflow.add_edge("send_reply", END)

# compile with checkpointer for persistence, in case run graph with local_server --> Please compile without checkpointer
memory = MemorySaver()
app = workflow.compile(checkpointer=memory)

# Test with an urgent billing issue
initial_state = {
    "email_content": "I was charged twice for my subscription! This is urgent!",
    "sender_email": "customer@example.com",
    "email_id": "email_123",
    "messages": []
}

# Run with a thread_id for persistence
config = {"configurable": {"thread_id": "customer_123"}}
result = app.invoke(initial_state, config)
# The graph will pause at human_review
print(f"human review interrupt:{result['__interrupt__']}")

# When ready, provide human input to resume
from langgraph.types import Command

human_response = Command(
    # 与interrupt配合使用，预设响应
    resume={
        "approved": True,
        "edited_response": "We sincerely apologize for the double charge. I've initiated an immediate refund..."
    }
)

# Resume execution
final_result = app.invoke(human_response, config)
print(f"Email sent successfully!")