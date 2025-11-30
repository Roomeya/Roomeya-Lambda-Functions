import json
import boto3
from boto3.dynamodb.conditions import Attr

dynamodb = boto3.resource("dynamodb")

results_table = dynamodb.Table("Roomeya-Results")
students_table = dynamodb.Table("Roomeya-Students")
forms_table = dynamodb.Table("Roomeya-Forms")

def lambda_handler(event, context):

    # 1) Path Parameter 확인
    path_params = event.get("pathParameters") or {}
    form_id = path_params.get("formId")

    if not form_id:
        return {
            "statusCode": 400,
            "headers": {"Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": "formId path parameter is required"})
        }

    # 2) 폼 통계 정보 가져오기
    form_item = forms_table.get_item(Key={"formId": form_id}).get("Item", {})
    
    total_participants = int(form_item.get("totalParticipants", 0))
    completed_count = int(form_item.get("completedCount", 0))
    
    # 0 미만 방지
    not_completed = max(0, total_participants - completed_count)

    # 3) 매칭 결과 조회
    response = results_table.scan(
        FilterExpression=Attr("formId").eq(form_id)
    )
    items = response.get("Items", [])

    male_results = []
    female_results = []

    # 4) 데이터 가공
    for item in items:
        members = item.get("members", [])
        
        # DB의 "uuid_room-0001" -> 프론트용 "room-0001" 로 변환
        raw_room_id = item.get("roomId", "")
        if "_" in raw_room_id:
            display_room_id = raw_room_id.split("_")[-1]
        else:
            display_room_id = raw_room_id

        memberA = None
        memberB = None

        # --- A 학생 ---
        if len(members) > 0:
            sidA = members[0]
            try:
                resA = students_table.get_item(Key={"studentId": sidA})
                memberA = resA.get("Item", {"studentId": sidA})
            except:
                memberA = {"studentId": sidA}

        # --- B 학생 ---
        if len(members) > 1:
            sidB = members[1]
            try:
                resB = students_table.get_item(Key={"studentId": sidB})
                memberB = resB.get("Item", {"studentId": sidB})
            except:
                memberB = {"studentId": sidB}

        # 프론트엔드 반환 객체
        room_result = {
            "roomId": display_room_id,   # 깔끔한 ID
            "score": item.get("score", 0),
            "memberA": memberA,
            "memberB": memberB
        }

        # 5) 성별 분류
        gender = memberA.get("gender", "") if memberA else ""

        if gender.startswith("남"):
            male_results.append(room_result)
        elif gender.startswith("여"):
            female_results.append(room_result)
        else:
            # 예외처리 (프론트 에러 방지)
            female_results.append(room_result)

    # 방 번호순 정렬 (room-0001, room-0002 ...)
    male_results.sort(key=lambda x: x["roomId"])
    female_results.sort(key=lambda x: x["roomId"])

    # 6) 최종 응답
    response_body = {
        "formId": form_id,
        "totalParticipants": total_participants,
        "completedCount": completed_count,
        "notCompletedCount": not_completed,
        "maleResults": male_results,
        "femaleResults": female_results
    }

    return {
        "statusCode": 200,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Content-Type": "application/json"
        },
        "body": json.dumps(response_body, ensure_ascii=False, default=str)
    }
