import json
import boto3
import uuid
from datetime import datetime

dynamodb = boto3.resource('dynamodb')
forms_table = dynamodb.Table('Roomeya-Forms')
responses_table = dynamodb.Table('Roomeya-FormResponses')
students_table = dynamodb.Table('Roomeya-Students')

def lambda_handler(event, context):
    try:
        # body 파싱
        if 'body' in event:
            body = json.loads(event['body'])
        else:
            body = event

        form_id = body.get('formId')
        studentId = body.get('studentId')
        name = body.get('name')
        answers = body.get('answers', [])

        if not form_id or not studentId or not name:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'formId, studentId, name이 필요합니다'}, ensure_ascii=False)
            }

        # form 존재 확인
        form_response = forms_table.get_item(Key={'formId': form_id})
        if 'Item' not in form_response:
            return {
                'statusCode': 404,
                'body': json.dumps({'error': '존재하지 않는 formId입니다'}, ensure_ascii=False)
            }

        # 응답 데이터 생성
        response_id = str(uuid.uuid4())
        response_data = {
            'responseId': response_id,
            'formId': form_id,
            'studentId': studentId,
            'name': name,
            'answers': answers,
            'submittedAt': datetime.now().isoformat()
        }

        # (1) FormResponses 테이블에 응답 저장
        responses_table.put_item(Item=response_data)

        # -------------------------------------------
        # (2) Roomeya-Forms: completedCount = completedCount + 1
        # -------------------------------------------
        forms_table.update_item(
            Key={'formId': form_id},
            UpdateExpression="SET completedCount = if_not_exists(completedCount, :zero) + :inc",
            ExpressionAttributeValues={
                ':inc': 1,
                ':zero': 0
            }
        )

        # -------------------------------------------
        # (3) Roomeya-Students: completed = True 업데이트
        # -------------------------------------------
        students_table.update_item(
            Key={'studentId': studentId},
            UpdateExpression="SET completed = :done",
            ExpressionAttributeValues={':done': True}
        )

        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'application/json'
            },
            'body': json.dumps({
                'message': '응답이 제출되었습니다',
                'responseId': response_id
            }, ensure_ascii=False)
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'application/json'
            },
            'body': json.dumps({'error': str(e)}, ensure_ascii=False)
        }
