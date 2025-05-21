import os
import csv
import threading

class DataLoader:

    data_list = []
    csv_file_path = os.getcwd() + '/data/test_data.csv'
    _lock = threading.Lock()  # Add thread lock for thread safety

    @staticmethod
    def load_data():
        DataLoader.data_list = []  # Clear existing data
        reader = csv.DictReader(open(DataLoader.csv_file_path))
        for row in reader:
            DataLoader.data_list.append(row)

    @staticmethod
    def get_data():
        with DataLoader._lock:  # Thread-safe access to data
            if len(DataLoader.data_list) < 1:
                raise IndexError("No more test data available")
            data_obj = DataLoader.data_list.pop(0)  # Get first item
            return data_obj.copy()  # Return a copy to prevent data sharing between users