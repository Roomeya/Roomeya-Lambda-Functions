import json
import boto3
from decimal import Decimal

dynamodb = boto3.resource("dynamodb")
form_table = dynamodb.Table("Roomeya-Forms")

# Decimal → int 변환 함수
def convert_decimal(obj):
    if isinstance(obj, list):
        return [convert_decimal(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: convert_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, Decimal):
        return int(obj)
    return obj


def lambda_handler(event, context):
    try:
        # 전체 폼 조회 (Scan)
        response = form_table.scan()
        items = response.get("Items", [])

        results = []

        for form in items:
            total = form.get("totalParticipants", 0)
            completed = form.get("completedCount", 0)

            result_item = {
                "formId": form.get("formId"),
                "title": form.get("title"),
                "deadline": form.get("deadline"),
                "createdAt": form.get("createdAt"),
                "totalParticipants": total,
                "completedCount": completed,
                "notCompletedCount": max(int(total) - int(completed), 0)
            }

            results.append(result_item)

        # Decimal → int 변환
        clean_results = convert_decimal(results)

        return {
            "statusCode": 200,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json"
            },
            "body": json.dumps(clean_results, ensure_ascii=False)
        }

    except Exception as e:
        print("Error:", e)
        return {
            "statusCode": 500,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json"
            },
            "body": json.dumps({"error": str(e)}, ensure_ascii=False)
        }
