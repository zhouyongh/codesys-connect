# -*- coding: utf-8 -*-
# online_ops.py - codesys-connect backend (CODESYS --runscript, IronPython 2.7)
# Compact one-line results. One op per run via target.txt (env CODESYS_CONNECT_TARGET).
#
# target.txt keys:
#   op=connect|disconnect|read|write|download|start|stop|status|login|logout
#   project=<abs .project path>
#   result=<output file>
#   log=<log file>            (optional)
#   user= password=           (device login credentials)
#   device=                   (device name under project, default: first PLC device)
#   app=                      (application name, default: first Application)
#   vars=a,b,c                (read)
#   pairs=name=value;name2=v2 (write, ';' separated)
#   change=Force|Try|Keep|Never   (login/download online-change option)
#
# result file: one status line + optional `name=value` lines. Nothing else.

import os
import traceback

TARGET = os.environ.get("CODESYS_CONNECT_TARGET") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "target.txt")


def load_cfg(path):
    cfg = {}
    f = open(path, "r")
    try:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip()
    finally:
        f.close()
    return cfg


CFG = load_cfg(TARGET)
RESULT = CFG.get(u"result", u"")
LOG = CFG.get(u"log", u"")
OUT = []


def log(msg):
    s = unicode(msg)
    if LOG:
        try:
            f = open(LOG, "a")
            f.write(s + u"\n")
            f.close()
        except Exception:
            pass
    # only keep ERR/fatal in the compact result via out(); debug stays in log
    if s.startswith(u"ERR") or s.startswith(u"WARN"):
        OUT.append(s)


def out(line):
    OUT.append(unicode(line))


def flush():
    if not RESULT:
        return
    f = open(RESULT, "w")
    try:
        f.write(u"\n".join(OUT) + u"\n")
    finally:
        f.close()


def fatal(msg):
    log(u"ERR " + unicode(msg))
    flush()
    # do not raise - CODESYS exit code is meaningless; result file is truth


def find_app(proj):
    name = CFG.get(u"app", u"")
    apps = []
    def walk(o, prefix):
        try:
            if getattr(o, u"is_application", False):
                full = prefix
                apps.append((full, o))
                return
        except Exception:
            pass
        try:
            kids = o.get_children() or []
        except Exception:
            kids = []
        for k in kids:
            try:
                nm = unicode(k.get_name())
            except Exception:
                nm = u"?"
            full = prefix + u"/" + nm if prefix else nm
            walk(k, full)
    for top in (proj.get_children() or []):
        try:
            nm = unicode(top.get_name())
        except Exception:
            nm = u"?"
        walk(top, nm)
    if not apps:
        try:
            a = proj.active_application
            if a:
                return (unicode(getattr(a, u"get_name", lambda: u"Application")()), a)
        except Exception:
            pass
        return (None, None)
    if name:
        for full, a in apps:
            if full == name or full.endswith(u"/" + name):
                return (full, a)
            try:
                if unicode(a.get_name()) == name:
                    return (full, a)
            except Exception:
                pass
    return apps[0]


def find_device(proj):
    name = CFG.get(u"device", u"")
    found = []
    def consider(o, nm):
        is_dev = False
        try:
            is_dev = bool(getattr(o, u"is_device", False))
        except Exception:
            is_dev = False
        # SoftMotion / Control / PLC root devices
        if (not is_dev) and (u"SoftMotion" in nm or u"Control" in nm or nm == u"Device"):
            is_dev = True
        if is_dev and nm.lower() not in (u"library manager", u"task configuration"):
            if name:
                if nm == name:
                    found.append(o)
            elif not found:
                found.append(o)
    def walk(o, prefix):
        if found and name:
            return
        try:
            kids = o.get_children() or []
        except Exception:
            kids = []
        for k in kids:
            try:
                nm = unicode(k.get_name())
            except Exception:
                nm = u"?"
            consider(k, nm)
            if not (found and name):
                walk(k, prefix + u"/" + nm if prefix else nm)
    for top in (proj.get_children() or []):
        try:
            nm = unicode(top.get_name())
        except Exception:
            nm = u"?"
        consider(top, nm)
        if not (found and name):
            walk(top, nm)
    return found[0] if found else None


def ensure_gateway(dev):
    """Configure device communication (local SoftMotion / Control Win)."""
    gw_name = CFG.get(u"gateway", u"Gateway-1")
    address = CFG.get(u"address", u"127.0.0.1")
    port = CFG.get(u"port", u"11740")
    dev_name = CFG.get(u"device_name", u"")
    if not dev_name:
        dev_name = CFG.get(u"device", u"Device")

    cs = None
    try:
        cs = dev.get_device_communication_settings()
        log(u"comm_settings device_name=%r address=%r gw=%r" % (
            getattr(cs, u"device_name", u"?"),
            getattr(cs, u"device_address", u"?"),
            getattr(cs, u"gateway_guid", u"?")))
    except Exception as e:
        log(u"comm_settings err=%r" % (e,))

    # resolve IScriptGateway
    gateway = None
    try:
        gws = online.gateways
        try:
            found = list(gws.find_with_name(gw_name))
            if found:
                gateway = found[0]
        except Exception as e:
            log(u"find_with_name err=%r" % (e,))
        if gateway is None:
            try:
                gateway = gws[0]
            except Exception as e:
                log(u"gws[0] err=%r" % (e,))
    except Exception as e:
        log(u"gateways err=%r" % (e,))
    log(u"gateway obj=%r" % (gateway,))

    # preferred: fill communication settings directly
    try:
        if cs is not None:
            try:
                cs.device_name = dev_name
            except Exception as e:
                log(u"cs.device_name err=%r" % (e,))
            try:
                if port and port not in address:
                    cs.device_address = u"%s:%s" % (address, port)
                else:
                    cs.device_address = address
            except Exception as e:
                log(u"cs.device_address err=%r" % (e,))
            try:
                if gateway is not None:
                    cs.gateway_guid = gateway.guid
            except Exception as e:
                log(u"cs.gateway_guid err=%r" % (e,))
            log(u"comm_settings updated name=%s addr=%s" % (dev_name, cs.device_address))
    except Exception as e:
        log(u"comm_settings write err=%r" % (e,))

    # also call set_gateway_* helpers (some builds require them)
    try:
        if gateway is not None:
            try:
                dev.set_gateway_and_ip_address(gateway, address, int(port) if port else 11740)
                log(u"set_gateway_and_ip_address ok")
            except Exception as e:
                log(u"set_gateway_and_ip_address err=%r" % (e,))
                try:
                    dev.set_gateway_and_device_name(gateway, dev_name)
                    log(u"set_gateway_and_device_name ok")
                except Exception as e2:
                    log(u"set_gateway_and_device_name err=%r" % (e2,))
        else:
            try:
                dev.set_gateway_and_device_name(gw_name, dev_name)
                log(u"set_gateway_and_device_name(%s,%s) ok" % (gw_name, dev_name))
            except Exception as e:
                log(u"set_gateway_and_device_name(string) err=%r" % (e,))
    except Exception as e:
        log(u"WARN set_gateway: %r" % (e,))


def get_online_app(create=True):
    """Return (project, device_obj, app_obj, online_dev, online_app) - parts may be None."""
    proj_path = CFG.get(u"project", u"")
    if not proj_path or not os.path.isfile(proj_path):
        fatal(u"project not found: " + proj_path)
        return (None, None, None, None, None)
    proj = projects.open(proj_path)
    # optional tree dump (debug=1 in target.txt) - off by default to stay compact
    if CFG.get(u"debug", u"") in (u"1", u"true", u"yes"):
        def dump(o, prefix, depth):
            if depth > 3:
                return
            try:
                kids = o.get_children() or []
            except Exception:
                kids = []
            for k in kids:
                try:
                    nm = unicode(k.get_name())
                except Exception:
                    nm = u"?"
                try:
                    is_app = bool(getattr(k, u"is_application", False))
                    is_dev = bool(getattr(k, u"is_device", False))
                except Exception:
                    is_app = is_dev = False
                log(u"tree %s%s app=%s dev=%s" % (prefix, nm, is_app, is_dev))
                dump(k, prefix + nm + u"/", depth + 1)
        try:
            for top in (proj.get_children() or []):
                try:
                    nm = unicode(top.get_name())
                except Exception:
                    nm = u"?"
                log(u"tree top=%s" % nm)
                dump(top, nm + u"/", 1)
        except Exception as e:
            log(u"tree dump err=%r" % (e,))

    app_full, app = find_app(proj)
    dev = find_device(proj)
    log(u"found app=%s dev=%s" % (app_full, unicode(dev.get_name()) if dev else None))
    if app is None:
        fatal(u"no Application in project")
        return (proj, dev, None, None, None)

    user = CFG.get(u"user", u"")
    password = CFG.get(u"password", u"")
    if user:
        try:
            online.set_default_credentials(user, password)
        except Exception:
            try:
                online.set_default_credentials(user)
            except Exception as e:
                log(u"WARN set_default_credentials: %r" % (e,))

    if dev is not None:
        ensure_gateway(dev)

    online_dev = None
    online_app = None
    if create:
        try:
            online_dev = online.create_online_device(dev)
        except Exception as e:
            log(u"WARN create_online_device: %r" % (e,))
            try:
                online_dev = online.create_online_device()
            except Exception as e2:
                fatal(u"create_online_device failed: %r" % (e2,))
                return (proj, dev, app, None, None)
        try:
            online_app = online.create_online_application(app)
        except Exception as e:
            fatal(u"create_online_application failed: %r" % (e,))
            return (proj, dev, app, online_dev, None)
    return (proj, dev, app, online_dev, online_app)


def ensure_connected(odeve, oapp, dev=None):
    """Connect + login (same as op_connect)."""
    try:
        odeve.connect()
    except Exception as e:
        log(u"WARN connect: %r" % (e,))
    change_name = CFG.get(u"change", u"Try")
    try:
        change = getattr(OnlineChangeOption, change_name)
    except Exception:
        change = OnlineChangeOption.Try
    try:
        oapp.login(change, False)
    except Exception:
        try:
            oapp.login(OnlineChangeOption.Force, False)
        except Exception as e:
            log(u"WARN login: %r" % (e,))
            return False
    return True


def op_status():
    proj, dev, app, odeve, oapp = get_online_app(create=True)
    if oapp is None:
        out(u"ERR no online application")
        return
    # auto-connect so status is useful on a fresh session
    ensure_connected(odeve, oapp, dev)
    try:
        connected = False
        user = u""
        try:
            connected = bool(odeve.connected) if odeve else False
            if odeve:
                try:
                    user = unicode(odeve.current_logged_on_username)
                except Exception:
                    user = u""
        except Exception:
            pass
        logged = bool(oapp.is_logged_in) if oapp else False
        astate = unicode(oapp.application_state) if oapp else u"?"
        ostate = unicode(oapp.operation_state) if oapp else u"?"
        out(u"connected=%s user=%s logged_in=%s app_state=%s op_state=%s" % (
            connected, user, logged, astate, ostate))
    except Exception as e:
        fatal(u"status: %r" % (e,))


def op_connect():
    proj, dev, app, odeve, oapp = get_online_app(create=True)
    if odeve is None:
        out(u"ERR no online device")
        return
    try:
        odeve.connect()
    except Exception as e:
        fatal(u"connect device: %r" % (e,))
        return
    # also login the application (downloads if needed) so read/write work
    change_name = CFG.get(u"change", u"Try")
    try:
        change = getattr(OnlineChangeOption, change_name)
    except Exception:
        change = OnlineChangeOption.Try
    try:
        oapp.login(change, False)
    except Exception as e:
        # try Force once
        try:
            oapp.login(OnlineChangeOption.Force, False)
        except Exception as e2:
            fatal(u"login: %r / force: %r" % (e, e2))
            return
    try:
        user = unicode(odeve.current_logged_on_username)
    except Exception:
        user = CFG.get(u"user", u"")
    out(u"OK connected=1 logged_in=1 user=%s app=%s" % (
        user, unicode(app.get_name()) if app else u"?"))


def op_login():
    # login only (device assumed connected)
    proj, dev, app, odeve, oapp = get_online_app(create=True)
    if oapp is None:
        return
    change_name = CFG.get(u"change", u"Try")
    try:
        change = getattr(OnlineChangeOption, change_name)
    except Exception:
        change = OnlineChangeOption.Try
    try:
        try:
            odeve.connect()
        except Exception:
            pass
        oapp.login(change, False)
        out(u"OK logged_in=1")
    except Exception as e:
        fatal(u"login: %r" % (e,))


def op_logout():
    proj, dev, app, odeve, oapp = get_online_app(create=True)
    if oapp is not None:
        try:
            oapp.logout()
        except Exception as e:
            log(u"WARN logout: %r" % (e,))
    if odeve is not None:
        try:
            odeve.disconnect()
        except Exception as e:
            log(u"WARN disconnect: %r" % (e,))
    out(u"OK logged_in=0")


def op_disconnect():
    op_logout()


def op_download():
    proj, dev, app, odeve, oapp = get_online_app(create=True)
    if oapp is None or odeve is None:
        return
    try:
        odeve.connect()
    except Exception as e:
        fatal(u"connect: %r" % (e,))
        return
    change_name = CFG.get(u"change", u"Force")
    try:
        change = getattr(OnlineChangeOption, change_name)
    except Exception:
        change = OnlineChangeOption.Force
    try:
        oapp.login(change, True)
    except Exception as e:
        try:
            oapp.login(OnlineChangeOption.Force, True)
        except Exception as e2:
            fatal(u"download/login: %r / %r" % (e, e2))
            return
    try:
        st = unicode(oapp.application_state)
        op = unicode(oapp.operation_state)
        out(u"OK downloaded=1 app_state=%s op_state=%s" % (st, op))
    except Exception:
        out(u"OK downloaded=1")


def op_start():
    proj, dev, app, odeve, oapp = get_online_app(create=True)
    if oapp is None:
        return
    try:
        try:
            odeve.connect()
        except Exception:
            pass
        if not oapp.is_logged_in:
            try:
                oapp.login(OnlineChangeOption.Try, False)
            except Exception:
                oapp.login(OnlineChangeOption.Force, False)
        oapp.start()
        out(u"OK started=1 op_state=%s" % unicode(oapp.operation_state))
    except Exception as e:
        fatal(u"start: %r" % (e,))


def op_stop():
    proj, dev, app, odeve, oapp = get_online_app(create=True)
    if oapp is None:
        return
    try:
        try:
            odeve.connect()
        except Exception:
            pass
        if not oapp.is_logged_in:
            try:
                oapp.login(OnlineChangeOption.Try, False)
            except Exception:
                oapp.login(OnlineChangeOption.Force, False)
        oapp.stop()
        out(u"OK stopped=1 op_state=%s" % unicode(oapp.operation_state))
    except Exception as e:
        fatal(u"stop: %r" % (e,))


def op_read():
    names = CFG.get(u"vars", u"")
    exprs = [x.strip() for x in names.split(u",") if x.strip()]
    if not exprs:
        fatal(u"read: no vars")
        return
    proj, dev, app, odeve, oapp = get_online_app(create=True)
    if oapp is None:
        return
    try:
        try:
            odeve.connect()
        except Exception:
            pass
        if not oapp.is_logged_in:
            try:
                oapp.login(OnlineChangeOption.Try, False)
            except Exception:
                oapp.login(OnlineChangeOption.Force, False)
        try:
            vals = oapp.read_values(exprs)
            for i, name in enumerate(exprs):
                v = vals[i] if i < len(vals) else u"?"
                out(u"%s=%s" % (name, unicode(v)))
        except Exception:
            # fallback one-by-one
            for name in exprs:
                try:
                    v = oapp.read_value(name)
                    out(u"%s=%s" % (name, unicode(v)))
                except Exception as e:
                    out(u"%s=ERR %s" % (name, unicode(e)))
    except Exception as e:
        fatal(u"read: %r" % (e,))


def op_write():
    pairs_raw = CFG.get(u"pairs", u"")
    if not pairs_raw:
        fatal(u"write: no pairs")
        return
    pairs = []
    for item in pairs_raw.split(u";"):
        item = item.strip()
        if not item or u"=" not in item:
            continue
        k, v = item.split(u"=", 1)
        pairs.append((k.strip(), v.strip()))
    if not pairs:
        fatal(u"write: empty pairs")
        return
    proj, dev, app, odeve, oapp = get_online_app(create=True)
    if oapp is None:
        return
    try:
        try:
            odeve.connect()
        except Exception:
            pass
        if not oapp.is_logged_in:
            try:
                oapp.login(OnlineChangeOption.Try, False)
            except Exception:
                oapp.login(OnlineChangeOption.Force, False)
        for name, val in pairs:
            try:
                oapp.set_prepared_value(name, val)
            except Exception as e:
                out(u"ERR %s prepare: %s" % (name, unicode(e)))
                continue
        try:
            oapp.write_prepared_values()
        except Exception as e:
            # fallback: direct write via write if prepared path fails
            for name, val in pairs:
                try:
                    # some builds expose write via set_prepared + write_prepared only
                    pass
                except Exception:
                    pass
            fatal(u"write_prepared_values: %r" % (e,))
            return
        for name, val in pairs:
            out(u"%s=%s" % (name, val))
        out(u"OK written=%d" % len(pairs))
    except Exception as e:
        fatal(u"write: %r" % (e,))


OPS = {
    u"connect": op_connect,
    u"login": op_login,
    u"logout": op_logout,
    u"disconnect": op_disconnect,
    u"download": op_download,
    u"start": op_start,
    u"stop": op_stop,
    u"read": op_read,
    u"write": op_write,
    u"status": op_status,
}

try:
    op = CFG.get(u"op", u"status")
    fn = OPS.get(op)
    if fn is None:
        fatal(u"unknown op: " + op)
    else:
        fn()
except Exception:
    fatal(traceback.format_exc())
flush()
