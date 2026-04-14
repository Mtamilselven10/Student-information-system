class Config:
    SECRET_KEY = "#DEEPDIVETECHNOLOGISTICS123"
    SQLALCHEMY_DATABASE_URI = 'sqlite:///quiz.sqlite3'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

   # -------- MAIL CONFIG --------
    MAIL_SERVER = "smtp.gmail.com"
    MAIL_PORT = 465
    MAIL_USE_SSL = True
    MAIL_USE_TLS = False

    MAIL_USERNAME = "tamilselvan2us@gmail.com"
    MAIL_PASSWORD = "uhbh rkxa gkrl ajww"   # 👈 ONLY ONE password (app password)

    MAIL_DEFAULT_SENDER = "tamilselvan2us@gmail.com"