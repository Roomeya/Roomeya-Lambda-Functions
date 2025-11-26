import json
import boto3

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table("Roomeya-Students")

def lambda_handler(event, context):
    try:
        # body 파싱
        body = json.loads(event.get("body", "{}"))

        student_id = body.get("studentId")
        name = body.get("name")

        if not student_id or not name:
            return {
                "statusCode": 400,
                "body": json.dumps({"message": "studentId and name are required"})
            }

        # DynamoDB 조회
        response = table.get_item(Key={"studentId": student_id})

        if "Item" not in response:
            # 학생 없음
            return {
                "statusCode": 200,
                "body": json.dumps({"match": False})
            }

        student = response["Item"]

        # 이름 대조
        is_match = (student.get("name") == name)

        return {
            "statusCode": 200,
            "body": json.dumps({"isValid": is_match})
        }

    except Exception as e:
        print("Error:", e)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
