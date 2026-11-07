"""Dedicated local OCR recipe, separate from the answer model."""
import base64
from .local_model import LocalModel

GLM_PROMPT='Text Recognition:'

def make_request(settings,image,max_tokens=4096):
    model=settings.get('ocr_model','glm-ocr')
    if model!='glm-ocr':raise ValueError('This OCR recipe requires the original glm-ocr identifier')
    return {'model':model,'messages':[{'role':'user','content':[{'type':'image_url','image_url':{'url':'data:image/png;base64,'+image}},{'type':'text','text':GLM_PROMPT}]}],'temperature':0,'max_tokens':max_tokens,'stream':False}

def validate_request(body,settings):
    if not isinstance(body,dict) or body.get('model')!=settings.get('ocr_model','glm-ocr') or body.get('model')!='glm-ocr':raise ValueError('OCR model refused')
    if set(body)!={'model','messages','temperature','max_tokens','stream'}:raise ValueError('Unexpected OCR parameters')
    if body['temperature']!=0 or body['stream'] is not False or not isinstance(body['max_tokens'],int) or not 1<=body['max_tokens']<=6000:raise ValueError('Invalid OCR generation settings')
    messages=body['messages']
    if not isinstance(messages,list) or len(messages)!=1 or messages[0].get('role')!='user':raise ValueError('Invalid OCR messages')
    content=messages[0].get('content')
    if not isinstance(content,list) or len(content)!=2 or content[0].get('type')!='image_url' or content[1]!={'type':'text','text':GLM_PROMPT}:raise ValueError('Invalid OCR content')
    url=content[0].get('image_url',{}).get('url','')
    if not url.startswith('data:image/png;base64,') or len(url)>8*1024*1024:raise ValueError('Only bounded inline PNG input is allowed')
    data=base64.b64decode(url.split(',',1)[1],validate=True)
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('Invalid PNG input')
    return body

def transcribe(home,image):
    model=LocalModel(home);body=validate_request(make_request(model.config,image),model.config)
    response=model.request('/v1/chat/completions',body)
    if response.get('model')!=body['model']:raise ValueError('OCR response model identity mismatch')
    choice=response['choices'][0]
    if choice.get('finish_reason')=='length':raise ValueError('Truncated OCR requires review')
    text=choice['message'].get('content') or ''
    if not isinstance(text,str):raise ValueError('Invalid OCR reply')
    return text,response
