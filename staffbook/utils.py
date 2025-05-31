import requests

def extract_text_from_image(image_path_or_url, api_key):
    url = 'https://api.ocr.space/parse/image'

    with open(image_path_or_url, 'rb') as image_file:
        result = requests.post(
            url,
            files={'filename': image_file},
            data={
                'apikey': api_key,
                'language': 'jpn',  # 日语
                'isOverlayRequired': False,
            }
        )

    result_json = result.json()
    if result_json['IsErroredOnProcessing']:
        return None
    return result_json['ParsedResults'][0]['ParsedText']
