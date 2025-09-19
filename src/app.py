Sep 19 07:41:43 tastypayment.aeza.network systemd[1]: Started vpn_bot.service -
Hiddify Telegram Bot Service.
Sep 19 07:41:43 tastypayment.aeza.network python[754814]: Traceback (most recent call last):
Sep 19 07:41:43 tastypayment.aeza.network python[754814]:   File "/opt/vpn-bot/src/main_bot.py", line 8, in <module>
Sep 19 07:41:43 tastypayment.aeza.network python[754814]:     from app import build_application
Sep 19 07:41:43 tastypayment.aeza.network python[754814]:   File "/opt/vpn-bot/src/app.py", line 233
Sep 19 07:41:43 tastypayment.aeza.network python[754814]:     ],
Sep 19 07:41:43 tastypayment.aeza.network python[754814]:     ^
Sep 19 07:41:43 tastypayment.aeza.network python[754814]: SyntaxError: closing parenthesis ']' does not match opening parenthesis '{' on line 212
Sep 19 07:41:43 tastypayment.aeza.network systemd[1]: vpn_bot.service: Main process exited, code=exited, status=1/FAILURE
Sep 19 07:41:43 tastypayment.aeza.network systemd[1]: vpn_bot.service: Failed with result 'exit-code'.