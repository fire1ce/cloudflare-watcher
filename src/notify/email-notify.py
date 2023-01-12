import smtplib
import validators
import sys

# sys.path.append("../../src/")

# import "logger" from "src/main.py"
from cloudflare_watcher import logger


# params
smtp_server = "smtp.gmail.com"
smtp_port = 587
smtp_login = "madseclab0@gmail.com"
smtp_password = "rdrmzvddtstvfhgy"
smtp_from = "cloudflare-watcher@3os.re"
smtp_to = "stas@3os.org"
smtp_subject = "cloudflare-watcher"
smtp_message = "testing testing 1 2 3"


def validation_error(variable_name, variable):
    logger.error(f"Invalid {variable_name}: {variable}")
    exit(1)


def is_valid_smtp_server(smtp_server):
    return validators.domain(smtp_server) or validators.ipv4(smtp_server)


def is_valid_smtp_port(smtp_port):
    return isinstance(smtp_port, int)


def is_valid_smtp_login(smtp_login):
    return validators.email(smtp_login)


def is_valid_smtp_password(smtp_password):
    return smtp_password != ""


def is_valid_smtp_from(smtp_from):
    return validators.email(smtp_from)


def is_valid_smtp_to(smtp_to):
    return validators.email(smtp_to)


def is_valid_smtp_subject(smtp_subject):
    return smtp_subject != ""


def is_valid_smtp_message(smtp_message):
    return smtp_message != ""


def validate_params():
    if not is_valid_smtp_server(smtp_server):
        validation_error("smtp_server", smtp_server)
    if not is_valid_smtp_port(smtp_port):
        validation_error("smtp_port", smtp_port)
    if not is_valid_smtp_login(smtp_login):
        validation_error("smtp_login", smtp_login)
    if not is_valid_smtp_password(smtp_password):
        validation_error("smtp_password", smtp_password)
    if not is_valid_smtp_from(smtp_from):
        validation_error("smtp_from", smtp_from)
    if not is_valid_smtp_to(smtp_to):
        validation_error("smtp_to", smtp_to)
    if not is_valid_smtp_subject(smtp_subject):
        validation_error("smtp_subject", smtp_subject)
    if not is_valid_smtp_message(smtp_message):
        validation_error("smtp_message", smtp_message)


def send_email():
    validate_params()
    try:
        # Create an SMTP object
        smtp = smtplib.SMTP(smtp_server, smtp_port)

        # Start the TLS (Transport Layer Security) for the connection
        smtp.ehlo()
        if smtp.has_extn("STARTTLS"):
            smtp.starttls()
            smtp.ehlo()
        if "auth" in smtp.esmtp_features:
            # Test the connection with the login credentials
            try:
                smtp.login(smtp_login, smtp_password)
            except smtplib.SMTPAuthenticationError as error:
                print("The login credentials are incorrect. Error: " + str(error))
                return
            except Exception as error:
                print("An error occurred while trying to login. Error: " + str(error))
                return

        # Create the message
        message = f"Subject: {smtp_subject}\n\n{smtp_message}"

        # Send the email
        smtp.sendmail(smtp_from, smtp_to, message)

        # Close the SMTP connection
        smtp.quit()
    except Exception as e:
        logger.error("An error occurred while sending the email: " + str(e))
        return
    print("Email sent successfully")
