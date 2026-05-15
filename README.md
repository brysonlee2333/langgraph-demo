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