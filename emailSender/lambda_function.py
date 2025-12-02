import json
import boto3
from boto3.dynamodb.conditions import Attr

dynamodb = boto3.resource("dynamodb")
ses = boto3.client("ses")

RESULTS_TABLE = "Roomeya-Results"
STUDENTS_TABLE = "Roomeya-Students"
RESPONSES_TABLE = "Roomeya-FormResponses"

SENDER_EMAIL = "sjisno1@dongguk.edu"  # SES 인증 이메일


def lambda_handler(event, context):
    try:
        # body 파싱
        body = json.loads(event.get("body", "{}"))
        form_id = body.get("formId")

        if not form_id:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "formId is required"})
            }

        students_table = dynamodb.Table(STUDENTS_TABLE)
        results_table = dynamodb.Table(RESULTS_TABLE)
        responses_table = dynamodb.Table(RESPONSES_TABLE)

        # 1) 매칭 결과 가져오기
        result_scan = results_table.scan(
            FilterExpression=Attr("formId").eq(form_id)
        )
        match_rooms = result_scan.get("Items", [])

        # roomId → member list 매핑
        room_map = {}
        for room in match_rooms:
            members = room.get("members", [])
            for sid in members:
                room_map[sid] = room

        # 2) 전체 응답자 조회
        res = responses_table.scan(
            FilterExpression=Attr("formId").eq(form_id)
        )
        form_responses = res.get("Items", [])

        # 3) 모든 학생에게 이메일 발송
        for item in form_responses:
            try:
                student_id = item["studentId"]

                # 학생 정보 조회
                stu = students_table.get_item(Key={"studentId": student_id}).get("Item")
                if not stu:
                    continue

                email = stu.get("email")
                name = stu.get("name", "학생")

                student_room = room_map.get(student_id)

                if student_room:
                    # 매칭된 경우
                    members = student_room.get("members", [])
                    partner = [sid for sid in members if sid != student_id]
                    partner_id = partner[0] if partner else None

                    partner_info = None
                    if partner_id:
                        partner_info = students_table.get_item(
                            Key={"studentId": partner_id}
                        ).get("Item")

                    html_body = build_html_email_matched(
                        name=name,
                        room_id=student_room.get("roomId"),
                        score=student_room.get("score", 0),
                        partner_info=partner_info
                    )
                else:
                    # 매칭되지 않은 사람
                    html_body = build_html_email_unmatched(name)

                # 이메일 발송
                if is_dummy_email(email):
                    print(f"⚠️ Skip dummy email: {email}")
                else:
                    send_html_email(
                        to=email,
                        subject="🛏 기숙사 매칭 결과 안내",
                        html_body=html_body
                    )

            except Exception as e:
                print(f"❌ Error sending email for student {item}: {str(e)}")
                # 계속 진행 (중단되지 않도록)

        return {
            "statusCode": 200,
            "body": json.dumps({"message": "Email process completed"})
        }

    except Exception as e:
        print(f"❌ Fatal error: {str(e)}")
        # 여기서도 200 리턴하여 프런트 오류 방지
        return {
            "statusCode": 200,
            "body": json.dumps({"message": "Email process completed with warnings"})
        }


def build_html_email_matched(name, room_id, score, partner_info):
    partner_html = ""

    if partner_info:
        partner_html = f"""
        <p><strong>파트너 정보</strong></p>
        <ul>
            <li>이름: {partner_info.get("name")}</li>
            <li>학번: {partner_info.get("studentId")}</li>
            <li>이메일: {partner_info.get("email")}</li>
        </ul>
        """

    return f"""
    <html>
    <head>
        <style>
            .box {{
                padding: 20px;
                border-radius: 10px;
                background: #f8f9fa;
                border: 1px solid #ddd;
                font-family: Arial, sans-serif;
            }}
            .title {{
                font-size: 20px;
                font-weight: bold;
                margin-bottom: 15px;
            }}
            .info {{
                margin-bottom: 10px;
            }}
        </style>
    </head>
    <body>
        <div class="box">
            <div class="title">{name}님, 기숙사 배정 안내드립니다.</div>

            <p class="info">배정된 방 번호: <strong>{room_id}</strong></p>
            <p class="info">매칭 점수: <strong>{score}</strong></p>

            {partner_html}

            <p style="margin-top:20px;">궁금한 사항이 있다면 언제든지 사무실로 문의해주세요.</p>
        </div>
    </body>
    </html>
    """


def build_html_email_unmatched(name):
    return f"""
    <html>
    <head>
        <style>
            .box {{
                padding: 20px;
                border-radius: 10px;
                background: #fff3cd;
                border: 1px solid #ffeeba;
                font-family: Arial, sans-serif;
            }}
            .title {{
                font-size: 20px;
                font-weight: bold;
                margin-bottom: 15px;
            }}
        </style>
    </head>
    <body>
        <div class="box">
            <div class="title">{name}님, 매칭 결과 안내</div>
            <p>아쉽게도 이번 매칭에서 함께 배정된 학생이 없습니다.</p>
            <p>단독 방 또는 추가 배정 절차가 진행될 예정입니다.</p>
        </div>
    </body>
    </html>
    """


def send_html_email(to, subject, html_body):
    ses.send_email(
        Source=SENDER_EMAIL,
        Destination={"ToAddresses": [to]},
        Message={
            "Subject": {"Data": subject, "Charset": "UTF-8"},
            "Body": {
                "Html": {"Data": html_body, "Charset": "UTF-8"}
            }
        }
    )


def is_dummy_email(email):
    dummy_patterns = ["@mail.com", "@test.com"]

    # 메일이 없거나 @ 포함 안 되어있으면 더미 취급
    if not email or "@" not in email:
        return True

    for p in dummy_patterns:
        if email.endswith(p):
            return True

    # user00xx@mail.com 같은 패턴
    if email.startswith("user00"):
        return True

    return False
