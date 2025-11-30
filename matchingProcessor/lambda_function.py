import json
import boto3
from boto3.dynamodb.conditions import Attr
import csv
import io
from datetime import datetime

dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")

FORM_TABLE = "Roomeya-FormResponses"
STUDENTS_TABLE = "Roomeya-Students"
RESULT_TABLE = "Roomeya-Results"
BUCKET = "roomeya-export"


# -----------------------------
#  점수 계산 로직
# -----------------------------
def calc_bedtime_similarity(b1, b2):
    similar_pairs = [("10to12", "12to2"), ("12to2", "after2")]
    if b1 == b2: return True
    for a, b in similar_pairs:
        if (b1 == a and b2 == b) or (b1 == b and b2 == a): return True
    return False

def calc_score(a, b):
    if a["gender"] != b["gender"]: return -1
    score = 0
    if a["smoking"] == b["smoking"]: score += 15
    if a["wakeup"] == b["wakeup"]: score += 8
    if calc_bedtime_similarity(a["bedtime"], b["bedtime"]): score += 8
    if a["mbti"] and b["mbti"] and a["mbti"][0] == b["mbti"][0]: score += 3
    return score

# -----------------------------
#  S3 저장 (CSV) - ID 깔끔하게 자르기
# -----------------------------
def save_to_s3_csv(formId, final_rooms):
    key = f"matching-results/{formId}.csv"
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["formId", "roomId", "studentA", "studentB", "score", "matchType"])

    for room in final_rooms:
        m = room["members"]
        a = m[0]
        b = m[1] if len(m) > 1 else ""
        
        # [CSV용 ID 정제] "uuid_room-0001" -> "room-0001"
        raw_id = room["roomId"]
        clean_id = raw_id.split("_")[-1] if "_" in raw_id else raw_id
        
        writer.writerow([formId, clean_id, a, b, room["score"], room.get("type", "preference")])

    s3.put_object(
        Bucket=BUCKET, 
        Key=key, 
        Body=output.getvalue().encode("utf-8"), 
        ContentType="text/csv"
    )
    return key


# -----------------------------
#  Lambda Handler
# -----------------------------
def lambda_handler(event, context):
    formId = event.get("formId")
    if not formId:
        return {"statusCode": 400, "body": "formId is required"}

    form_table = dynamodb.Table(FORM_TABLE)
    student_table = dynamodb.Table(STUDENTS_TABLE)
    result_table = dynamodb.Table(RESULT_TABLE)

    print(f"🟦 Starting Matching for Form: {formId}")

    # ====================================================
    # 0) 기존 결과 삭제 (초기화)
    # ====================================================
    try:
        # formId로 조회해서 roomId(PK)를 찾아 삭제
        scan_res = result_table.scan(
            FilterExpression=Attr("formId").eq(formId),
            ProjectionExpression="roomId"
        )
        old_items = scan_res.get("Items", [])
        
        if old_items:
            print(f"🟥 Deleting {len(old_items)} old records...")
            with result_table.batch_writer() as batch:
                for item in old_items:
                    batch.delete_item(Key={"roomId": item["roomId"]})
    except Exception as e:
        print(f"⚠️ Cleanup Warning: {str(e)}")

    # ====================================================
    # 1) 데이터 로드 (필터링 적용)
    # ====================================================
    
    # A. 설문 응답자 (해당 폼)
    resp_res = form_table.scan(FilterExpression=Attr("formId").eq(formId))
    form_items = resp_res.get("Items", [])
    
    # B. [핵심] 전체 학생 목록 (해당 폼에 등록된 학생만!!)
    # 폼 생성 시 저장된 formId를 기준으로 필터링합니다.
    stu_res = student_table.scan(
        FilterExpression=Attr("formId").eq(formId)
    )
    all_students = stu_res.get("Items", [])
    
    student_map = {s["studentId"]: s for s in all_students}
    
    print(f"🟦 Loaded: {len(form_items)} responses, {len(all_students)} total students in this form.")

    # C. 응답자 객체화
    respondents = []
    
    for item in form_items:
        sid = item["studentId"]
        s_info = student_map.get(sid)
        
        # 학생 명부에 없는 사람이 응답한 경우 스킵 
        if not s_info: 
            continue 

        respondents.append({
            "studentId": sid,
            "gender": s_info.get("gender", ""),
            "smoking": item["answers"].get("smoking"),
            "wakeup": item["answers"].get("wakeup"),
            "bedtime": item["answers"].get("bedtime"),
            "mbti": item["answers"].get("mbti", "")
        })

    # ====================================================
    # 2) Phase 1: 취향 매칭 (Score > 0)
    # ====================================================
    potential_pairs = []
    for i in range(len(respondents)):
        for j in range(i + 1, len(respondents)):
            score = calc_score(respondents[i], respondents[j])
            if score >= 0:
                potential_pairs.append({
                    "members": [respondents[i]["studentId"], respondents[j]["studentId"]],
                    "score": score
                })
    
    potential_pairs.sort(key=lambda x: x["score"], reverse=True)

    used_ids = set()
    final_rooms = []
    room_cnt = 1

    for pair in potential_pairs:
        a, b = pair["members"]
        if a in used_ids or b in used_ids: continue
        
        used_ids.add(a)
        used_ids.add(b)
        
        # DB용 유니크 ID 생성
        u_rid = f"{formId}_room-{room_cnt:04d}"
        
        final_rooms.append({
            "roomId": u_rid,
            "members": [a, b],
            "score": pair["score"],
            "type": "preference"
        })
        room_cnt += 1

    # ====================================================
    # 3) Phase 2: 잔여 인원 매칭 (Score 0, 학번순)
    # ====================================================
    # 전체 학생(이 폼에 속한) 중 매칭 안 된 사람
    leftover_ids = [sid for sid in student_map.keys() if sid not in used_ids]
    
    male_pool = []
    female_pool = []
    
    for sid in leftover_ids:
        stu = student_map.get(sid, {})
        g = stu.get("gender", "")
        
        if g.startswith("남"): male_pool.append(sid)
        elif g.startswith("여"): female_pool.append(sid)
        else: female_pool.append(sid) 

    # 학번순 정렬 -> 인접한 학번끼리 매칭
    male_pool.sort()
    female_pool.sort()

    def create_random_matches(pool, counter):
        rooms = []
        for i in range(0, len(pool), 2):
            m = [pool[i]]
            if i+1 < len(pool): m.append(pool[i+1])
            
            u_rid = f"{formId}_room-{counter:04d}"
            rooms.append({
                "roomId": u_rid,
                "members": m,
                "score": 0,
                "type": "random_id"
            })
            counter += 1
        return rooms, counter

    m_rooms, room_cnt = create_random_matches(male_pool, room_cnt)
    final_rooms.extend(m_rooms)
    
    f_rooms, room_cnt = create_random_matches(female_pool, room_cnt)
    final_rooms.extend(f_rooms)

    print(f"🟩 Total Rooms Generated: {len(final_rooms)}")

    # ====================================================
    # 4) 저장
    # ====================================================
    with result_table.batch_writer() as batch:
        for room in final_rooms:
            batch.put_item(
                Item={
                    "roomId": room["roomId"],  # PK (Unique)
                    "formId": formId,
                    "members": room["members"],
                    "score": room["score"],
                    "matchType": room["type"],
                    "createdAt": datetime.utcnow().isoformat()
                }
            )

    csv_key = save_to_s3_csv(formId, final_rooms)

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Matching completed",
            "totalRooms": len(final_rooms),
            "csvKey": csv_key
        })
    }
