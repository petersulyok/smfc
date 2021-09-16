#!/bin/bash

coverage run -m unittest discover ./test
coverage html
