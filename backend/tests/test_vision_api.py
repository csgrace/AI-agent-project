import os
from openai import OpenAI
import base64
from dotenv import load_dotenv

load_dotenv()

# 配置阿里云百炼的API
client = OpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

# 你的图片路径
image_path = r"D:\E\SUSTECH\grade3\3down\CS\software_engineering\team-project-26spring-26s-22\backend\data\tis_download\full_course_table\screenshots\page_1.png"

# 读取图片并转成base64
def encode_image(image_path):
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode()

img_base64 = encode_image(image_path)

# 调用视觉模型
response = client.chat.completions.create(
    model="qwen3-vl-32b-thinking",  # 使用视觉模型
    messages=[
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "请识别这张课程表，提取所有课程信息，输出为JSON格式。"},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{img_base64}"  # 图片格式改为png
                    }
                }
            ]
        }
    ]
)

# 打印结果
print(response.choices[0].message.content)