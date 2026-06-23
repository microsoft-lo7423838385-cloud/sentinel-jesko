##this is for custom functions only
##no new function name will be accepted
##predefined functions are only allowed to be used
##do not modify if you dont know what your doing
##follow the guidelines


def attachment_obfuscate(attach_value):
    #param (attach_value) -> string
    ##this is for html or text attachments only
    ##do what ever you want with attachment before send
    ##make sure to return a value
    return attach_value
    
def letter_obfuscate(letter_value): 
    #param (letter_value) -> string
    ##do what ever you want with letter before sending
    ##make sure to return a value
    return letter_value
    
def image_obfuscate(image_value):
    ##param (image_value) -> bytes
    ##do what ever you want with image files before sending
    ##make sure to return a value
    return image_value
 
def attachment_modify(attachment_value):
    ##param (attachment_value) -> bytes
    ##this is for all types of attachment [Zip,pdf,txt] and all kinds
    ##do what ever you want with letter before send
    ##make sure to return a value
    #print(len(attachment_value))
    return attachment_value
    
def header_modify(header_values):
    ##param (header_values) -> dict
    ##modify the headers of the message before sending
    ##dont uses .items() or any dict related methods, only access as dict
    ##header_values["your-new-header"] = "your-new-header-values"
    return header_values