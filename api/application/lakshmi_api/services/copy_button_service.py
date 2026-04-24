class CopyButtonService:
    def __init__(self, attributes_dict):
        self.attributes_dict = attributes_dict

    def process(self, json_data):
        for key in json_data:
            if key not in self.attributes_dict:
                continue
            json_data[key] = {
                "value": json_data[key],
                "copy_button": True if self.attributes_dict[key] else False
            }
        return json_data
