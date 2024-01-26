from . import base
from . import exception
from . import datatypes
from maya import cmds
from maya import mel as _mel
from maya.api import OpenMaya
import functools


SCOPE_ATTR = 0
SCOPE_NODE = 1


__all__ = []

Callback = functools.partial
displayError = OpenMaya.MGlobal.displayError
displayInfo = OpenMaya.MGlobal.displayInfo
displayWarning = OpenMaya.MGlobal.displayWarning
# TODO : None to list


class _Mel(object):
    __Instance = None

    def __new__(self):
        if _Mel.__Instance is None:
            _Mel.__Instance = super(_Mel, self).__new__(self)
            _Mel.__Instance.__cmds = {}
            _Mel.__Instance.eval = _mel.eval

        return _Mel.__Instance

    def __init__(self):
        super(_Mel, self).__init__()

    def __wrap_mel(self, melcmd, *args):
        argstr = ", ".join([x.__repr__() for x in args])
        return super(_Mel, self).__getattribute__("eval")("{}({})".format(melcmd, argstr))

    def __getattribute__(self, name):
        try:
            return super(_Mel, self).__getattribute__(name)
        except AttributeError:
            cache = super(_Mel, self).__getattribute__("_Mel__cmds")
            if name in cache:
                return cache[name]

            if name == "eval":
                return super(_Mel, self).__getattribute__("eval")

            incmd = getattr(cmds, name, None)
            if incmd is not None:
                cache[name] = _pymaya_cmd_wrap(incmd, wrap_object=False)
                return cache[name]

            res = super(_Mel, self).__getattribute__("eval")("whatIs {}".format(name))
            if res.endswith(".mel"):
                cache[name] = functools.partial(super(_Mel, self).__getattribute__("_Mel__wrap_mel"), name)
                return cache[name]

            raise


mel = _Mel()


def exportSelected(*args, **kwargs):
    cmds.file(*args, es=True, **kwargs)


def hasAttr(obj, attr, checkShape=True):
    obj = _obj_to_name(obj)

    has = cmds.attributeQuery(attr, n=obj, ex=True)
    if not has and checkShape:
        shapes = cmds.listRelatives(obj, s=True) or []
        for s in shapes:
            has = cmds.attributeQuery(attr, n=s, ex=True)
            if has:
                break

    return has


def selected(**kwargs):
    return _name_to_obj(cmds.ls(sl=True, **kwargs))


class versions():
    def current():
        return cmds.about(api=True)


def importFile(filepath, **kwargs):
    return _name_to_obj(cmds.file(filepath, i=True, **kwargs))


def sceneName():
    return cmds.file(q=True, sn=True)


class MayaGUIs(object):
    def GraphEditor(self):
        cmds.GraphEditor()

runtime = MayaGUIs()


def confirmBox(title, message, yes="Yes", no="No", *moreButtons, **kwargs):
    ret = cmds.confirmDialog(t=title, m=message, b=[yes, no] + list(moreButtons), db=yes, ma="center", cb=no, ds=no)
    if moreButtons:
        return ret
    else:
        return (ret == yes)


def _obj_to_name(arg):
    if isinstance(arg, (list, set, tuple)):
        return arg.__class__([_obj_to_name(x) for x in arg])
    elif isinstance(arg, dict):
        newdic = {}
        for k, v in arg.items():
            newdic[k] = _obj_to_name(v)
        return newdic
    elif isinstance(arg, base.Base):
        return arg.name()
    else:
        return arg


def _dt_to_value(arg):
    if isinstance(arg, (list, set, tuple)):
        return arg.__class__([_dt_to_value(x) for x in arg])
    elif isinstance(arg, datatypes.Vector):
        return [arg[0], arg[1], arg[2]]
    elif isinstance(arg, datatypes.Point):
        return [arg[0], arg[1], arg[2], arg[3]]
    elif isinstance(arg, datatypes.Matrix):
        return [arg[0], arg[1], arg[2], arg[3],
                arg[4], arg[5], arg[6], arg[7],
                arg[8], arg[9], arg[10], arg[11],
                arg[12], arg[13], arg[14], arg[15]]
    else:
        return arg


def _name_to_obj(arg, scope=SCOPE_NODE, known_node=None):
    # lazy importing
    from . import bind

    if isinstance(arg, (list, set, tuple)):
        return arg.__class__([_name_to_obj(x, scope=scope, known_node=known_node) for x in arg])

    elif isinstance(arg, str):
        if (scope == SCOPE_ATTR and known_node is not None):
            try:
                return bind.PyNode("{}.{}".format(known_node, arg))
            except:
                return arg
        else:
            try:
                return bind.PyNode(arg)
            except:
                return arg
    else:
        return arg


def _pymaya_cmd_wrap(func, wrap_object=True, scope=SCOPE_NODE):
    def wrapper(*args, **kwargs):
        args = _obj_to_name(args)
        kwargs = _obj_to_name(kwargs)

        res = func(*args, **kwargs)

        if wrap_object:
            known_node = None
            if scope == SCOPE_ATTR:
                candi = None

                if args:
                    known_node = args[0]
                else:
                    sel = cmds.ls(sl=True)
                    if sel:
                        known_node = sel[0]

                if known_node is not None:
                    if not isinstance(_name_to_obj(known_node), base.Base):
                        known_node = None

            return _name_to_obj(res, scope=scope, known_node=known_node)
        else:
            return res

    return wrapper


def _getAttr(*args, **kwargs):
    args = _obj_to_name(args)
    kwargs = _obj_to_name(kwargs)

    try:
        res = cmds.getAttr(*args, **kwargs)
    except Exception as e:
        raise exception.MayaAttributeError(*e.args)

    if isinstance(res, list) and len(res) > 0:
        at = cmds.getAttr(args[0], type=True)
        if isinstance(res[0], tuple):
            if at == "pointArray":
                return [datatypes.Vector(x) for x in res]
            elif at == "vectorArray":
                return [datatypes.Point(x) for x in res]

            if at.endswith("3"):
                return datatypes.Vector(res[0])

            return res[0]
        else:
            if at == "vectorArray":
                return [datatypes.Vector(res[i], res[i + 1], res[i + 2]) for i in range(0, len(res), 3)]
            elif at == "matrix":
                return datatypes.Matrix(res)

            return res

    return res


def _setAttr(*args, **kwargs):
    args = _dt_to_value(_obj_to_name(args))
    kwargs = _obj_to_name(kwargs)

    try:
        fargs = []
        for arg in args:
            if isinstance(arg, (list, set, tuple)):
                fargs.extend(arg)
            else:
                fargs.append(arg)

        if len(fargs) == 2 and isinstance(fargs[1], str) and "typ" not in kwargs and "type" not in kwargs:
            kwargs["type"] = "string"

        cmds.setAttr(*fargs, **kwargs)
    except Exception as e:
        raise exception.MayaAttributeError(*e.args)


def _currentTime(*args, **kwargs):
    if not args and not kwargs:
        kwargs["query"] = True

    return cmds.currentTime(*args, **kwargs)


def _keyframe(*args, **kwargs):
    args = _obj_to_name(args)
    kwargs = _obj_to_name(kwargs)

    t = kwargs.pop("time", kwargs.pop("k", None))
    if t is not None:
        if isinstance(t, (int, float)):
            kwargs["time"] = (t,)
        else:
            kwargs["time"] = t

    return cmds.keyframe(*args, **kwargs)


def _cutKey(*args, **kwargs):
    nargs = _obj_to_name(args)
    nkwargs = {}
    for k, v in kwargs.items():
        nkwargs[k] = _obj_to_name(v)

    t = nkwargs.pop("time", nkwargs.pop("k", None))
    if t is not None:
        if isinstance(t, (int, float)):
            nkwargs["time"] = (t,)
        else:
            nkwargs["time"] = t

    return cmds.cutKey(*nargs, **nkwargs)


def _bakeResults(*args, **kwargs):
    args = _obj_to_name(args)
    kwargs = _obj_to_name(kwargs)

    t = kwargs.pop("t", kwargs.pop("time", None))
    if t is not None:
        if isinstance(t, str) and ":" in t:
            t = tuple([float(x) for x in t.split(":")])
        kwargs["time"] = t

    return cmds.bakeResults(*args, **kwargs)


def _sets(*args, **kwargs):
    args = _obj_to_name(args)
    kwargs = _obj_to_name(kwargs)

    add = kwargs.pop("add", kwargs.pop("addElement", None))
    if add is not None and isinstance(add, list):
        for a in add:
            ckwargs = kwargs.copy()
            ckwargs["add"] = a
            cmds.sets(*args, **ckwargs)

        return _name_to_obj(args[0])

    return _name_to_obj(*args, **kwargs)


class _Cmd(object):
    __Instance = None
    __DO_NOT_CAST_FUNCS = set()
    __SCOPE_ATTR_FUNCS = {"listAttr"}

    def __new__(self):
        if _Cmd.__Instance is None:
            _Cmd.__Instance = super(_Cmd, self).__new__(self)
            _Cmd.__Instance.__initialize()

        return _Cmd.__Instance

    def __initialize(self):
        self.__cmds = {}
        self.__cmds["getAttr"] = _getAttr
        self.__cmds["setAttr"] = _setAttr
        self.__cmds["currentTime"] = _currentTime
        self.__cmds["keyframe"] = _keyframe
        self.__cmds["cutKey"] = _cutKey
        self.__cmds["bakeResults"] = _bakeResults
        self.__cmds["sets"] = _sets

    def __init__(self):
        super(_Cmd, self).__init__()

    def __getattribute__(self, name):
        try:
            return super(_Cmd, self).__getattribute__(name)
        except AttributeError:
            cache = super(_Cmd, self).__getattribute__("_Cmd__cmds")
            if name in cache:
                return cache[name]

            incmd = getattr(cmds, name, None)
            if incmd is not None:
                cache[name] = _pymaya_cmd_wrap(incmd, wrap_object=(name not in _Cmd.__DO_NOT_CAST_FUNCS), scope=SCOPE_ATTR if name in _Cmd.__SCOPE_ATTR_FUNCS else SCOPE_NODE)
                return cache[name]

            raise


cmd = _Cmd()
