# gate_configurations.py
# KHO LƯU TRỮ TRUNG TÂM CHO TẤT CẢ CÁC GATE CỦA BẠN

GATE_CONFIGS = {
    "link_1": {
        "formId": "250810145129839085",
        "currency": "CHF",
        "name_length_range": (15, 30),
        "email_config": {"text_length_range": (20, 30), "append_digits": 2},
        "payload": {
            "account_uuid":"82cf0802-2dca-420b-938a-737d0114a8d6","test_mode":False,"create_supporter":False,
            "supporter":{"locale":"fr","first_name":"{{first_name}}","last_name":"{{last_name}}","email":"{{email}}","street":"{{street}}","house_number":"{{house_number}}","postal_code":"{{postal_code}}","city":"{{city}}"},
            "raisenow_parameters":{
                "analytics":{"channel":"paylink","preselected_amount":"2000","suggested_amounts":"[2000,3000,10000]","user_agent":"{{user_agent}}"},
                "solution":{"uuid":"d7dcb288-dde0-462c-b19b-8fdd4aa45a22","name":"Homepage - Mitgliedschaft 2025 Zeitungsinserat","type":"donate"},
                "product":{"name":"tamaro","source_url":"https://donate.raisenow.io/ggyhj?lng=fr","uuid":"self-service","version":"2.16.0"},
                "integration":{"donation_receipt_requested":"false","message":"{{message}}"}
            },
            "custom_parameters":{"campaign_id":"Homepage","campaign_subid":""},
            "payment_information":{"brand_code":"eca","cardholder":"{{cardholder}}","expiry_month":"{{expiry_month}}","expiry_year":"{{expiry_year}}","transaction_id":"{{transaction_id}}"},
            "profile":"bd0064bf-aea3-424c-a66c-116fc98db4bd",
            "return_url":"https://donate.raisenow.io/ggyhj?lng=fr&rnw-view=payment_result"
        }
    },
    "link_2": {
        "formId": "250810144857559858",
        "currency": "EUR",
        "name_length_range": (15, 30),
        "email_config": {"text_length_range": (20, 30), "append_digits": 2},
        "payload": {
            "account_uuid":"69ca3b46-f6cc-44cb-accb-e19e3ba44622","test_mode":False,"create_supporter":False,
            "supporter":{"locale":"en","first_name":"{{first_name}}","last_name":"{{last_name}}","email":"{{email}}","street":"{{street}}","house_number":"{{house_number}}","postal_code":"{{postal_code}}","city":"{{city}}"},
            "raisenow_parameters":{
                "analytics":{"channel":"paylink","preselected_amount":"5000","suggested_amounts":"[5000,10000,15000]","user_agent":"{{user_agent}}"},
                "solution":{"uuid":"84421cf2-f451-45f8-a5f4-c1235d8ce96f","name":"Allgemeine Spenden","type":"donate"},
                "product":{"name":"tamaro","source_url":"https://donate.raisenow.io/zyspm?lng=en","uuid":"self-service","version":"2.16.0"}
            },
            "custom_parameters":{"campaign_id":"","campaign_subid":""},
            "payment_information":{"brand_code":"eca","cardholder":"{{cardholder}}","expiry_month":"{{expiry_month}}","expiry_year":"{{expiry_year}}","transaction_id":"{{transaction_id}}"},
            "profile":"dcf5b132-75e6-4232-8dec-6f8268bcd62e",
            "return_url":"https://donate.raisenow.io/zyspm?lng=en&rnw-view=payment_result"
        }
    },
    "link_3": {
        "formId": "250810145351258617",
        "currency": "CHF",
        "name_length_range": (15, 30),
        "email_config": {"text_length_range": (20, 30), "append_digits": 2},
        "payload": {
            "account_uuid":"82cf0802-2dca-420b-938a-737d0114a8d6","test_mode":False,"create_supporter":False,
            "supporter":{"locale":"fr","first_name":"{{first_name}}","last_name":"{{last_name}}","email":"{{email}}","street":"{{street}}","house_number":"{{house_number}}","postal_code":"{{postal_code}}","city":"{{city}}"},
            "raisenow_parameters":{
                "analytics":{"channel":"paylink","preselected_amount":"2000","suggested_amounts":"[2000,3000,10000]","user_agent":"{{user_agent}}"},
                "solution":{"uuid":"33ac4e7d-d1a3-49dd-a382-c742bc7eb09b","name":"Homepage","type":"donate"},
                "product":{"name":"tamaro","source_url":"https://donate.raisenow.io/kbndf?lng=fr","uuid":"self-service","version":"2.16.0"},
                "integration":{"donation_receipt_requested":"false","message":"{{message}}"}
            },
            "custom_parameters":{"campaign_id":"Homepage","campaign_subid":""},
            "payment_information":{"brand_code":"eca","cardholder":"{{cardholder}}","expiry_month":"{{expiry_month}}","expiry_year":"{{expiry_year}}","transaction_id":"{{transaction_id}}"},
            "profile":"bd0064bf-aea3-424c-a66c-116fc98db4bd",
            "return_url":"https://donate.raisenow.io/kbndf?lng=fr&rnw-view=payment_result"
        }
    },
    "link_4": {
        "formId": "250810145434568253",
        "currency": "CHF",
        "name_length_range": (15, 30),
        "email_config": {"text_length_range": (20, 30), "append_digits": 2},
        "payload": {
            "account_uuid":"ef52724d-70e1-4660-a3d3-c471a08619be","test_mode":False,"create_supporter":False,
            "supporter":{"locale":"fr","first_name":"{{first_name}}","last_name":"{{last_name}}","email_permission":False,"raisenow_parameters":{"integration":{"opt_in":{"email":False}}},"street":"{{street}}","house_number":"{{house_number}}","postal_code":"{{postal_code}}","city":"{{city}}"},
            "raisenow_parameters":{
                "analytics":{"channel":"paylink","preselected_amount":"5000","suggested_amounts":"[5000,10000,25000]","user_agent":"{{user_agent}}"},
                "solution":{"uuid":"ba3bd275-4954-432b-abef-a3e9c007a56c","name":"Spende via Homepage","type":"donate"},
                "product":{"name":"tamaro","source_url":"https://donate.raisenow.io/cyhfy?lng=fr","uuid":"self-service","version":"2.16.0"}
            },
            "custom_parameters":{"campaign_id":"Spende via Homepage","campaign_subid":""},
            "payment_information":{"brand_code":"eca","cardholder":"{{cardholder}}","expiry_month":"{{expiry_month}}","expiry_year":"{{expiry_year}}","transaction_id":"{{transaction_id}}"},
            "profile":"d19c23a0-be8e-4227-8d75-5bfc2ab2139d",
            "return_url":"https://donate.raisenow.io/cyhfy?lng=fr&rnw-view=payment_result"
        }
    },
    "link_5": {
        "formId": "250810145512358021",
        "currency": "EUR",
        "name_length_range": (15, 30),
        "email_config": {"text_length_range": (20, 30), "append_digits": 2},
        "payload": {
            "account_uuid":"69ca3b46-f6cc-44cb-accb-e19e3ba44622","test_mode":False,"create_supporter":False,
            "supporter":{"locale":"en","first_name":"{{first_name}}","last_name":"{{last_name}}","email":"{{email}}","street":"{{street}}","house_number":"{{house_number}}","postal_code":"{{postal_code}}","city":"{{city}}"},
            "raisenow_parameters":{
                "analytics":{"channel":"paylink","preselected_amount":"5000","suggested_amounts":"[5000,10000,15000]","user_agent":"{{user_agent}}"},
                "solution":{"uuid":"dd31d6a3-0bd7-420a-8048-67813225deee","name":"Spendenaufruf \"Roboterarm für Christoph\"","type":"donate"},
                "product":{"name":"tamaro","source_url":"https://donate.raisenow.io/ztszm?lng=en","uuid":"self-service","version":"2.16.0"}
            },
            "custom_parameters":{"campaign_id":"","campaign_subid":""},
            "payment_information":{"brand_code":"eca","cardholder":"{{cardholder}}","expiry_month":"{{expiry_month}}","expiry_year":"{{expiry_year}}","transaction_id":"{{transaction_id}}"},
            "profile":"dcf5b132-75e6-4232-8dec-6f8268bcd62e",
            "return_url":"https://donate.raisenow.io/ztszm?lng=en&rnw-view=payment_result"
        }
    },
    "link_6": {
        "formId": "250810145554928734",
        "currency": "EUR",
        "name_length_range": (15, 30),
        "email_config": {"text_length_range": (20, 30), "append_digits": 2},
        "payload": {
            "account_uuid":"69ca3b46-f6cc-44cb-accb-e19e3ba44622","test_mode":False,"create_supporter":False,
            "supporter":{"locale":"en","first_name":"{{first_name}}","last_name":"{{last_name}}","email":"{{email}}","street":"{{street}}","house_number":"{{house_number}}","postal_code":"{{postal_code}}","city":"{{city}}"},
            "raisenow_parameters":{
                "analytics":{"channel":"paylink","preselected_amount":"5000","suggested_amounts":"[5000,10000,15000]","user_agent":"{{user_agent}}"},
                "solution":{"uuid":"e0b3a84c-59b6-4957-98a0-f15a2e5381fd","name":"Spendenaufruf \"Behindertengerechter Umbau für Adrian\"","type":"donate"},
                "product":{"name":"tamaro","source_url":"https://donate.raisenow.io/ydbrd?lng=en","uuid":"self-service","version":"2.16.0"}
            },
            "custom_parameters":{"campaign_id":"","campaign_subid":""},
            "payment_information":{"brand_code":"eca","cardholder":"{{cardholder}}","expiry_month":"{{expiry_month}}","expiry_year":"{{expiry_year}}","transaction_id":"{{transaction_id}}"},
            "profile":"dcf5b132-75e6-4232-8dec-6f8268bcd62e",
            "return_url":"https://donate.raisenow.io/ydbrd?lng=en&rnw-view=payment_result"
        }
    },
    "link_7": {
        "formId": "250810145616689272",
        "currency": "CHF",
        "name_length_range": (15, 30),
        "email_config": {"text_length_range": (20, 30), "append_digits": 2},
        "payload": {
            "account_uuid":"8a3fa781-17a5-4898-b883-dea9f8eab4bd","test_mode":False,"create_supporter":False,
            "supporter":{"locale":"fr","first_name":"{{first_name}}","last_name":"{{last_name}}","street":"{{street}}","house_number":"{{house_number}}","postal_code":"{{postal_code}}"},
            "raisenow_parameters":{
                "analytics":{"channel":"paylink","preselected_amount":"2000","suggested_amounts":"[2000,5000,10000]","user_agent":"{{user_agent}}"},
                "solution":{"uuid":"3bc49af7-8a3d-4e42-9011-79c3150a561e","name":"Spendeformular","type":"donate"},
                "product":{"name":"tamaro","source_url":"https://donate.raisenow.io/hddtf?lng=fr","uuid":"self-service","version":"2.16.0"},
                "integration":{"donation_receipt_requested":"false"}
            },
            "custom_parameters":{"campaign_id":"","campaign_subid":""},
            "payment_information":{"brand_code":"eca","cardholder":"{{cardholder}}","expiry_month":"{{expiry_month}}","expiry_year":"{{expiry_year}}","transaction_id":"{{transaction_id}}"},
            "profile":"23c782a1-d4d6-4499-bbb8-9bcd7af24648",
            "return_url":"https://donate.raisenow.io/hddtf?lng=fr&rnw-view=payment_result"
        }
    }
}
