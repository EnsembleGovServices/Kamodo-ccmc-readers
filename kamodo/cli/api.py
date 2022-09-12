import os
from os import path

import numpy as np
import pandas as pd
from kamodo import kamodofy, Kamodo
from sympy.core.function import UndefinedFunction
from kamodo import get_defaults, getfullargspec


import flask
from flask import Flask, render_template, jsonify
from flask_cors import CORS, cross_origin
from flask_restful import reqparse, abort, Api, Resource

from io import StringIO
import json

import hydra
from hydra.experimental import compose
from omegaconf import OmegaConf


try:
    hydra.experimental.initialize(strict=False)
except:
    pass

app = Flask(__name__)

CORS(app) # enable Cross Origin Resource Sharing (CORS), making cross-origin AJAX possible.


def config_override(cfg):
    """Overrides with user-supplied configuration

    kamodo will override its configuration using
    kamodo.yaml if it is in the current working directory
    or users can set an override config:
        config_override=path/to/myconfig.yaml
    """
    if cfg.config_override is not None:
        override_path = hydra.utils.to_absolute_path(cfg.config_override)
        if path.exists(override_path):
            override_conf = OmegaConf.load(override_path)
            # merge overrides first input with second
            cfg = OmegaConf.merge(cfg, override_conf)
    return cfg


def get_api(app):
    """get restful api for this app"""
    api = Api(app)
    return api


def main():
    """main entrypoint"""

    cfg = compose('conf/kamodo.yaml')

    cli_conf = OmegaConf.from_cli()
    cfg = OmegaConf.merge(cfg, cli_conf)

    extra_files = []
    config_override_ = None
    if cfg.config_override is not None:
        override_path = "{}/{}".format(os.getcwd(), cfg.config_override)
        if path.exists(override_path):
            print("found {}".format(override_path))
            config_override_ = OmegaConf.load(override_path)
            # print(config_override.pretty())
            extra_files.append(override_path)
        else:
            if cfg.verbose > 0:
                print("could not get override: {}".format(override_path))

        if config_override_ is not None:
            cfg = OmegaConf.merge(cfg, config_override_)


    if cfg.verbose > 0:
        print(cfg.pretty())


    models = dict()
    for model_name, model_conf in cfg.models.items():
        try:
            # this might fail
            model_ = hydra.utils.instantiate(model_conf)
            models[model_name] = model_
        except:
            pass

    api = Api(app)


    class Models(Resource):
        def get(self):
            details = dict()
            for model_name, model_ in models.items():
                detail = model_.detail().astype(str)
                print(detail)
                details[model_name] = detail.to_dict(
                    # default_handler=str,
                    # indent =4,
                    orient='index',
                    )
            return details

    api.add_resource(Models, '/api', '/api/')


    for model_name, model_ in models.items():
        api.add_resource(
            get_model_resource(model_name, model_),
            '/api/{}'.format(model_name),
            '/api/{}/'.format(model_name),
            endpoint=model_name)

        for var_symbol in model_:
            if type(var_symbol) != UndefinedFunction:
                var_label = str(type(var_symbol))
                api.add_resource(
                    get_func_resource(model_name, model_, var_symbol),
                    '/api/{}/{}'.format(model_name, var_label),
                    endpoint='/'.join([model_name, var_label]))

        api.add_resource(
            get_evaluate_resource(model_name, model_),
            '/api/{}/evaluate'.format(model_name),
            endpoint='/'.join([model_name, 'evaluate'])
            )


    @app.route('/')
    def index():
        return 'Hello Flask app'

    app.run()


def get_model_resource(model_name, model):
    """Retrieve resource asscociated with this model"""

    class model_resource(Resource):
        """Resource for this model"""
        def get(self):
            """Get method for this model"""
            return model.detail().astype(str).to_dict(orient='index')

    return model_resource

def get_func_resource(model_name, model, var_symbol):
    """Get resource associated with this function"""
    parser = reqparse.RequestParser()
    func = model[var_symbol]
    defaults = get_defaults(func)

    for arg in getfullargspec(func).args:
        if arg in defaults:
            parser.add_argument(arg, type=str)
        else:
            parser.add_argument(arg, type=str, required=True)

    class FuncResource(Resource):
        """Resource associated with this function"""

        def get(self):
            """get method for this resource"""
            args_ = parser.parse_args(strict=True)
            args = dict()

            for argname, val_ in args_.items():
                args[argname] = pd.read_json(StringIO(val_), typ='series')

            return func(**args).tolist()
    return FuncResource

def get_evaluate_resource(model_name, model):
    """get resource associated with evaluate"""
    parser = reqparse.RequestParser()
    parser.add_argument('variable', type=str, required=True)

    for var_symbol in model:
        if type(var_symbol) != UndefinedFunction:
            func = model[var_symbol]
            for arg in getfullargspec(func).args:
                parser.add_argument(arg, type=str)



    class EvaluateResource(Resource):
        """Resource associated with evaluate"""

        def get(self):
            """get method for this resource"""
            args_ = parser.parse_args()
            args = dict()

            variable_name = ''

            for argname, val_ in args_.items():
                if argname != 'variable':
                    if val_ is not None:
                        args[argname] = pd.read_json(StringIO(val_), typ='series')

                else:
                    variable_name = val_

            try:
                result = model.evaluate(variable=variable_name, **args)
            except SyntaxError as m:
                return {'message': '{}'.format(m)}

            return {k_: v_.tolist() for k_, v_ in result.items()}

    return EvaluateResource


def get_plot_resource(model_name, model, var_symbol):
    """Get resource associated with this plot"""
    pass


if __name__ == '__main__':
    main()
