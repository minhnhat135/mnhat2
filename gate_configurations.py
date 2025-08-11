# gate_configurations.py
# KHO LƯU TRỮ TRUNG TÂM CHO TẤT CẢ CÁC GATE CỦA BẠN

GATE_CONFIGS = {
    "link_4": {
        "formId": "250811094232328649",
        "currency": "CHF",
        "name_length_range": (15, 30),
        "email_config": {"text_length_range": (20, 30), "append_digits": 2},
        "payload": {
            "account_uuid":"f8e678c2-f7b1-44b8-b77f-ad9291f904e2","test_mode":False,"create_supporter":False,
            "supporter":{
                "locale":"en",
                "first_name":"{{first_name}}",
                "last_name":"{{last_name}}",
                "email":"{{email}}",
                "email_permission":False,
                "raisenow_parameters":{"integration":{"opt_in":{"email":False}}}
            },
            "raisenow_parameters":{
                "analytics":{"channel":"paylink","preselected_amount":"5000","suggested_amounts":"[5000,10000,20000]","user_agent":"{{user_agent}}"},
                "solution":{"uuid":"709561d2-5d7c-418f-abfe-bf77e334d5b0","name":"Spenden","type":"donate"},
                "product":{"name":"tamaro","source_url":"https://donate.raisenow.io/gdmvq?lng=en","uuid":"self-service","version":"2.16.0"},
                "integration":{"donation_receipt_requested":"false"}
            },
            "custom_parameters":{"campaign_id":"","campaign_subid":""},
            "payment_information":{"brand_code":"eca","cardholder":"{{cardholder}}","expiry_month":"{{expiry_month}}","expiry_year":"{{expiry_year}}","transaction_id":"{{transaction_id}}"},
            "profile":"1a3ebefe-83d3-4df5-8020-a6f5e44ca81c",
            "return_url":"https://donate.raisenow.io/gdmvq?lng=en&rnw-view=payment_result"
        }
    },
    "link_5": {
        "formId": "250811094258459613",
        "currency": "CHF",
        "name_length_range": (15, 30),
        "email_config": {"text_length_range": (20, 30), "append_digits": 2},
        "payload": {
            "account_uuid":"f8e678c2-f7b1-44b8-b77f-ad9291f904e2","test_mode":False,"create_supporter":False,
            "supporter":{
                "locale":"en",
                "first_name":"{{first_name}}",
                "last_name":"{{last_name}}",
                "email":"{{email}}",
                "email_permission":False,
                "raisenow_parameters":{"integration":{"opt_in":{"email":False}}}
            },
            "raisenow_parameters":{
                "analytics":{"channel":"paylink","preselected_amount":"5000","suggested_amounts":"[5000,10000,20000]","user_agent":"{{user_agent}}"},
                "solution":{"uuid":"709561d2-5d7c-418f-abfe-bf77e334d5b0","name":"Spenden","type":"donate"},
                "product":{"name":"tamaro","source_url":"https://donate.raisenow.io/gdmvq?lng=en","uuid":"self-service","version":"2.16.0"},
                "integration":{"donation_receipt_requested":"false"}
            },
            "custom_parameters":{"campaign_id":"","campaign_subid":""},
            "payment_information":{"brand_code":"eca","cardholder":"{{cardholder}}","expiry_month":"{{expiry_month}}","expiry_year":"{{expiry_year}}","transaction_id":"{{transaction_id}}"},
            "profile":"1a3ebefe-83d3-4df5-8020-a6f5e44ca81c",
            "return_url":"https://donate.raisenow.io/gdmvq?lng=en&rnw-view=payment_result"
        }
    }
}
