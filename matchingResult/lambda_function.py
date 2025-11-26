import json
import boto3
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource("dynamodb")
results_table = dynamodb.Table("Roomeya-Results")
students_table = dynamodb.Table("Roomeya-Students")
forms_table = dynamodb.Table("Roomeya-Forms")

def lambda_handler(event, context):

    # Path parameter 읽기
    path_params = event.get("pathParameters", {})
    form_id = path_params.get("formId")

    if not form_id:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "formId path parameter is required"})
        }

    # 🔥 1. Roomeya-Forms에서 totalParticipants, completedCount 조회
    form_res = forms_table.get_item(Key={"formId": form_id})
    form_item = form_res.get("Item", {})

    total_participants = int(form_item.get("totalParticipants", 0))
    completed_count = int(form_item.get("completedCount", 0))
    not_completed_count = max(total_participants - completed_count, 0)

    # 🔥 2. 매칭 결과 조회
    response = results_table.query(
        KeyConditionExpression=Key("formId").eq(form_id)
    )

    items = response.get("Items", [])
    result_list = []

    for item in items:
        members = item.get("members", [])

        memberA = None
        memberB = None
        
        if len(members) > 0:
            sidA = members[0]
            resA = students_table.get_item(Key={"studentId": sidA})
            memberA = resA.get("Item", {"studentId": sidA})

        if len(members) > 1:
            sidB = members[1]
            resB = students_table.get_item(Key={"studentId": sidB})
            memberB = resB.get("Item", {"studentId": sidB})

        result_list.append({
            "roomId": item.get("roomId"),
            "score": item.get("score", 0),
            "memberA": memberA,
            "memberB": memberB
        })

    # 🔥 3. 최종 응답 구성
    final_response = {
        "formId": form_id,
        "totalParticipants": total_participants,
        "completedCount": completed_count,
        "notCompletedCount": not_completed_count,
        "results": result_list
    }

    return {
        "statusCode": 200,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Content-Type": "application/json"
        },
        "body": json.dumps(final_response, ensure_ascii=False, default=str)
    }
