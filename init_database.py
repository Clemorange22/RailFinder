from database import Database

def main():
    data_path = "data_sources.json"  # 确保这个文件在当前目录
    db = Database()
    db.load_and_prepare_data(data_path)
    print("✅ 初始化完成：GTFS 数据已成功载入数据库！")

if __name__ == "__main__":
    main()
