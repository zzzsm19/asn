import json
import datetime
from asn.utils.time import TIME_FORMAT

class DatetimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            # return "DATETIME:" + str(obj.timestamp())
            return obj.strftime(TIME_FORMAT)
        return json.JSONEncoder.default(self, obj)
    
class DatetimeDecoder(json.JSONDecoder):
    def __init__(self):
        json.JSONDecoder.__init__(self, object_hook=self.dict_to_object)
    
    def dict_to_object(self, d):
        # if d[:9] == "DATETIME:":
        #     return datetime.datetime.fromtimestamp(float(d[9:]))
        for key in d:
            if isinstance(d[key], str) and len(d[key]) == 19:
                try:
                    d[key] = datetime.datetime.strptime(d[key], TIME_FORMAT)
                except:
                    pass
        return d
