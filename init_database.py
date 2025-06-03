from database import Database

def main():
    data_path = "data_sources.json"  
    db = Database()
    db.load_and_prepare_data(data_path)
    print("✅ Database initialized and data loaded successfully.")

if __name__ == "__main__":
    main()

