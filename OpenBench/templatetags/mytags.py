from django import template

from OpenBench.models import Test

def oneDigitPrecision(value):
    try:
        value = round(value, 1)
        if "." not in str(value):
            return str(value) + ".0"
        pre, post = str(value).split(".")
        post += "0"
        return pre + "." + post[0:1]
    except:
        return value

def twoDigitPrecision(value):
    try:
        value = round(value, 2)
        if "." not in str(value):
            return str(value) + ".00"
        pre, post = str(value).split(".")
        post += "00"
        return pre + "." + post[0:2]
    except:
        return value

def gitDiffLink(test):

    if type(test) != Test:
        dev     = test["dev"]["source"]
        base    = test["base"]["source"]
        devsha  = test["dev"]["sha"]
        basesha = test["base"]["sha"]

    else:
        dev     = test.dev.source
        base    = test.base.source
        devsha  = test.dev.sha
        basesha = test.base.sha

    repo = "/".join(dev.split("/")[:-2])

    return "{0}/compare/{1}...{2}".format(repo, basesha[:8], testsha[:8])

register = template.Library()
register.filter("oneDigitPrecision", oneDigitPrecision)
register.filter("twoDigitPrecision", twoDigitPrecision)
register.filter("gitDiffLink", gitDiffLink)

