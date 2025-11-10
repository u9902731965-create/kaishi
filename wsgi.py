"""
WSGI配置文件 - 用于AlwaysData部署
"""
import os
import sys

# 添加项目目录到Python路径
project_home = os.path.dirname(__file__)
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# 导入Flask应用
from app import app as application

# AlwaysData会调用这个application对象
if __name__ == "__main__":
    application.run()
