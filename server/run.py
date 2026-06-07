"""服务入口:从 config 读端口,绑 0.0.0.0(局域网 Kindle 需能访问 Mac/NAS)。
端口改动需重启(端口不热重载);其余配置热重载,不必重启。
用法:python3 -m server.run
"""
import uvicorn

from server.app import app, cm


def main():
    port = int(cm.get().get("server", {}).get("port", 8585))
    print(f"Kindle Dashboard 启动:http://0.0.0.0:{port}  设置页:/setup")
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
