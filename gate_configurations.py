# gate_configurations.py
# KHO LƯU TRỮ TRUNG TÂM CHO TẤT CẢ CÁC GATE CỦA BẠN

GATE_CONFIGS = {
    "link_1": {
        "formId": "250810203247699080",
        "currency": "CHF",
        "name_length_range": (15, 30),
        "email_config": {"text_length_range": (20, 30), "append_digits": 2},
        "payload": {
            "account_uuid":"210fb5d6-377f-4313-a271-b27ed13afdff","test_mode":False,"create_supporter":False,
            "supporter":{
                "locale":"de",
                "first_name":"{{first_name}}",
                "last_name":"{{last_name}}",
                "email":"{{email}}",
                "street":"{{street}}",
                "house_number":"{{house_number}}",
                "postal_code":"{{postal_code}}",
                "city":"{{city}}",
                "country":"UM"
            },
            "raisenow_parameters":{
                "analytics":{"channel":"paylink","preselected_amount":"2500","suggested_amounts":"[2500,5000,7000,10000]","user_agent":"{{user_agent}}"},
                "solution":{"uuid":"39cb462b-8a20-4d09-b382-ea25ffa168d7","name":"Bartgeier-Namensspende","type":"donate"},
                "product":{"name":"tamaro","source_url":"https://donate.raisenow.io/vszmz?lng=de","uuid":"self-service","version":"2.16.0"},
                "integration":{"message":"{{message}}"}
            },
            "custom_parameters":{"campaign_id":"","campaign_subid":""},
            "payment_information":{"brand_code":"eca","cardholder":"{{cardholder}}","expiry_month":"{{expiry_month}}","expiry_year":"{{expiry_year}}","transaction_id":"{{transaction_id}}"},
            "profile":"5dbabae5-0890-402c-a396-43b36a583e63",
            "return_url":"https://donate.raisenow.io/vszmz?lng=de&rnw-view=payment_result"
        }
    },
    "link_2": {
        "formId": "250810203422729326",
        "currency": "CHF",
        "name_length_range": (15, 30),
        "email_config": {"text_length_range": (20, 30), "append_digits": 2},
        "payload": {
            "account_uuid":"d38666ec-f147-4e23-b5c8-ba30def24824","test_mode":False,"create_supporter":False,
            "supporter":{
                "locale":"de",
                "first_name":"{{first_name}}",
                "last_name":"{{last_name}}",
                "email":"{{email}}",
                "email_permission":False,
                "raisenow_parameters":{"integration":{"opt_in":{"email":False}}},
                "street":"{{street}}",
                "house_number":"{{house_number}}",
                "postal_code":"{{postal_code}}",
                "city":"{{city}}",
                "country":"US"
            },
            "raisenow_parameters":{
                "analytics":{"channel":"paylink","preselected_amount":"5000","suggested_amounts":"[5000,10000,15000]","user_agent":"{{user_agent}}"},
                "solution":{"uuid":"4b55b947-3fbe-4b01-91ed-668c2ae4e6e0","name":"Standardspende","type":"donate"},
                "product":{"name":"tamaro","source_url":"https://donate.raisenow.io/fxwsr?lng=de","uuid":"self-service","version":"2.16.0"}
            },
            "custom_parameters":{"campaign_id":"","campaign_subid":""},
            "payment_information":{"brand_code":"eca","cardholder":"{{cardholder}}","expiry_month":"{{expiry_month}}","expiry_year":"{{expiry_year}}","transaction_id":"{{transaction_id}}"},
            "profile":"ac53bad8-0abe-4ffb-8ed4-7b75af499857",
            "return_url":"https://donate.raisenow.io/fxwsr?lng=de&rnw-view=payment_result"
        }
    },
    "link_3": {
        "formId": "250811094153039668",
        "currency": "CHF",
        "name_length_range": (15, 30),
        "email_config": {"text_length_range": (20, 30), "append_digits": 2},
        "payload": {
            "account_uuid":"d38666ec-f147-4e23-b5c8-ba30def24824","test_mode":False,"create_supporter":False,
            "supporter":{
                "locale":"en",
                "first_name":"{{first_name}}",
                "last_name":"{{last_name}}",
                "email":"{{email}}",
                "email_permission":False,
                "raisenow_parameters":{"integration":{"opt_in":{"email":False}}},
                "street":"{{street}}",
                "house_number":"{{house_number}}",
                "postal_code":"{{postal_code}}",
                "city":"{{city}}",
                "country":"UM"
            },
            "raisenow_parameters":{
                "analytics":{"channel":"paylink","preselected_amount":"5000","suggested_amounts":"[5000,10000,15000]","user_agent":"{{user_agent}}"},
                "solution":{"uuid":"4b55b947-3fbe-4b01-91ed-668c2ae4e6e0","name":"Standardspende","type":"donate"},
                "product":{"name":"tamaro","source_url":"https://donate.raisenow.io/fxwsr?lng=en","uuid":"self-service","version":"2.16.0"}
            },
            "custom_parameters":{"campaign_id":"","campaign_subid":""},
            "payment_information":{"brand_code":"eca","cardholder":"{{cardholder}}","expiry_month":"{{expiry_month}}","expiry_year":"{{expiry_year}}","transaction_id":"{{transaction_id}}"},
            "profile":"ac53bad8-0abe-4ffb-8ed4-7b75af499857",
            "return_url":"https://donate.raisenow.io/fxwsr?lng=en&rnw-view=payment_result"
        }
    },
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
