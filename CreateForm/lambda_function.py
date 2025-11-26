import json
import boto3
import uuid
from datetime import datetime

dynamodb = boto3.resource('dynamodb')
form_table = dynamodb.Table('Roomeya-Forms')
student_table = dynamodb.Table('Roomeya-Students')

def lambda_handler(event, context):
    try:
        # Authorization header
        headers = event.get("headers", {})
        auth_header = headers.get("Authorization") or headers.get("authorization")

        token = None
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.replace("Bearer ", "").strip()

        # body
        body = json.loads(event.get("body", "{}"))

        form_id = str(uuid.uuid4())

        student_objs = body.get("participants", [])
        participants = []

        for stu in student_objs:
            sid = stu.get("studentId")
            if not sid:
                continue

            # 1) Students table 조회
            response = student_table.get_item(Key={"studentId": sid})
            student_item = response.get("Item")

            # 2) 없다면 새로 생성
            if not student_item:
                student_item = {
                    "studentId": sid,
                    "name": stu.get("name", ""),
                    "gender": stu.get("gender", ""),
                    "email": stu.get("email", ""),
                    "createdAt": datetime.utcnow().isoformat(),
                }

            # 학생에게 form 정보 및 완료 여부 추가
            student_item["completed"] = False
            student_item["formId"] = form_id

            # DB에 저장 (신규 / 기존 모두 업데이트)
            student_table.put_item(Item=student_item)

            # form.participants 에 넣기
            participants.append(student_item)

        # 폼 정보 생성
        form_data = {
            "formId": form_id,
            "title": body.get("title", "제목 없음"),
            "deadline": body.get("deadline"),
            "fields": body.get("fields", []),
            "participants": participants,
            "createdAt": datetime.utcnow().isoformat(),
            "createdBy": token,

            # 새로 추가되는 필드들
            "totalParticipants": len(participants),
            "completedCount": 0
        }

        form_table.put_item(Item=form_data)

        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'application/json'
            },
            'body': json.dumps({
                "message": "폼 생성 성공",
                "formId": form_id
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
            'body': json.dumps({"error": str(e)}, ensure_ascii=False)
        }
