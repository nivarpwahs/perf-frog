import csv
import os
from utils.log_helper import Logger


class DataLoader:
    data = []
    current_index = 0

    @staticmethod
    def load_data():
        try:
            data_path = os.path.join(os.getcwd(), 'data', 'test_data.csv')
            with open(data_path, 'r') as f:
                reader = csv.DictReader(f)
                DataLoader.data = list(reader)
            DataLoader.current_index = 0
        except Exception as e:
            Logger.log_message(f"Error loading test data: {str(e)}")

    @staticmethod
    def get_data():
        if DataLoader.current_index >= len(DataLoader.data):
            raise IndexError("No more test data available")
        
        data = DataLoader.data[DataLoader.current_index]
        DataLoader.current_index += 1
        return data