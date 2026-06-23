"""Pluggable transport adapters: SES and Office365 (lightweight implementations).

SES requires boto3 to be installed and AWS credentials available (environment, profile, or config).
Office365 adapter here is a simple SMTP-based adapter (placeholder for OAUTH2 flows).
"""
import logging

def send_via_ses(smtp_config, msg, envelope_from, recipient, logger=None):
    """
    Send via Amazon SES send_raw_email using boto3.
    AWS credentials are resolved from smtp_config when provided,
    otherwise boto3's default credential chain is used (SSO/env/profile).
    """
    try:
        import boto3
        from botocore.exceptions import NoCredentialsError, PartialCredentialsError, ClientError
    except Exception as e:
        if logger:
            logger.critical(f"boto3 is not installed. Cannot use SES. Error: {e}")
        return False

    try:
        region = getattr(smtp_config, 'aws_region', 'eu-north-1')
        if not region:
            region = 'eu-north-1'
        kwargs = {'region_name': region}
        ak = getattr(smtp_config, 'aws_access_key_id', None)
        sk = getattr(smtp_config, 'aws_secret_access_key', None)
        if ak and sk:
            kwargs['aws_access_key_id'] = ak
            kwargs['aws_secret_access_key'] = sk

        client = boto3.client('ses', **kwargs)
        raw_bytes = msg.as_string().encode('utf-8')
        to_header = (msg.get('To') or msg.get('to') or '').strip()
        logger.info(f"SES send_raw_email destinations={recipient!r} to_header={to_header!r} from_header={msg.get('From')!r} envelope_from={envelope_from!r}")
        resp = client.send_raw_email(
            RawMessage={'Data': raw_bytes},
            Destinations=[recipient],
        )
        if logger:
            logger.info(f"SES raw send success message_id={resp.get('MessageId')} to={recipient}")
        return True
    except PartialCredentialsError:
        if logger:
            logger.error("SES send failed: Incomplete AWS credentials in config and no default credential chain available.")
        return False
    except NoCredentialsError:
        if logger:
            logger.error("SES send failed: No AWS credentials found. Run 'aws login' or configure keys/region.")
        return False
    except ClientError as e:
        code = e.response.get('Error', {}).get('Code', 'Unknown')
        msg_text = e.response.get('Error', {}).get('Message', str(e))
        if logger:
            logger.error(f"SES send failed [{code}]: {msg_text} recipient={recipient}")
        return False
    except Exception as e:
        if logger:
            logger.error(f"SES send failed unexpectedly: {type(e).__name__}: {e}")
        return False


def send_via_office365(smtp_config, msg, envelope_from, recipient, logger=None):
    """Simple SMTP sender for Office365 (placeholder). Uses standard SMTP login.
    For production with Office365 modern auth, implement OAuth2.
    """
    import smtplib
    try:
        host = smtp_config.get('host')
        port = smtp_config.get('port', 587)
        security = smtp_config.get('security', 'starttls')
        if security == 'ssl' or port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=smtp_config.get('timeout', 30))
        else:
            server = smtplib.SMTP(host, port, timeout=smtp_config.get('timeout', 30))
            server.starttls()
        server.login(smtp_config.get('email'), smtp_config.get('password'))
        server.sendmail(envelope_from, [recipient], msg.as_string())
        try:
            server.quit()
        except Exception:
            pass
        return True
    except Exception as e:
        if logger:
            logger.warning(f"Office365 SMTP send failed: {e}")
        return False
