# sample_input.py
def process_user_data(data):
    # Untyped, legacy processing logic with potential runtime issues
    res = []
    for x in data:
        if x['active'] == True:
            res.append(x['name'].upper())
    return res