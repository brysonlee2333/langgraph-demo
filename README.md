# langgraph-demo

## 一、quick start
1.定义模型和tool，工具名默认为方法名，AI是通过docstring(注释)理解工具的作用，判断应该调用何种工具

2.定义graph's state,图的状态用来存储消息和其他的一些字段，在不同结点之间流转，结点返回的值追加到state中（**相同的key则覆盖，不同的key则追加**）

3.定义模型结点（调用模型）、工具结点（工具执行）、分支判断逻辑

4.构图：定义结点、定义边链接各个结点（jupyter可以直观展示图）
```python
# Show the agent
from IPython.display import Image, display
display(Image(agent.get_graph(xray=True).draw_mermaid_png()))
```
5.输出结果

## LangSmith使用
1.注册LangSmith，获取API_KEY

2.安装依赖
```
uv add langgraph-cli[inmem]
```

3.项目根目录添加langgraph.json文件，指定agent
```json
{
    "dependencies": ["."],
    "graphs": {
        "chief_agent": "practice/calculator_agent.py:agent"
    },
    "env": ".env"
}
```

4.项目根目录下执行命令，可以通过Studio UI查看细节，进行调试
```
langgraph dev
```

## Thinking in LangGraph
确定你想设计的agent的功能，及简单实现：很多以前看起来很复杂的功能，现在因为大模型能够识别语意，使用agent可以较容易的实现
Step 1: Map out your workflow as discrete steps 把要实现的功能拆分成功能明确的一个个步骤，然后用边相连

Step 2: identify what each step needs to do 识别每一步需要做的东西

Step 3: Design your state. state是图的共享存储
参考链接：https://docs.langchain.com/oss/python/langgraph/