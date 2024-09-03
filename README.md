<img align="right" width="128" height="128" src="https://raw.githubusercontent.com/gbbirkisson/gbb-ha/main/icon.svg">

<h1>GBB HA component bundle</h1>

[![GitHub release (latest SemVer)](https://img.shields.io/github/v/release/gbbirkisson/gbb-ha)](https://github.com/gbbirkisson/gbb-ha/releases)
[![GitHub last commit (branch)](https://img.shields.io/github/last-commit/gbbirkisson/gbb-ha/main)](https://github.com/gbbirkisson/gbb-ha/commits/main)
[![CI](https://github.com/gbbirkisson/gbb-ha/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/gbbirkisson/gbb-ha/actions/workflows/ci.yml)
[![codecov](https://codecov.io/github/gbbirkisson/gbb-ha/branch/main/graph/badge.svg?token=5VQHEBQ7JV)](https://codecov.io/github/gbbirkisson/gbb-ha)
[![GitHub](https://img.shields.io/github/license/gbbirkisson/gbb-ha)](https://github.com/gbbirkisson/gbb-ha/blob/main/LICENSE)

This is my humble [Home Assistant](https://www.home-assistant.io/) custom component bundle.
These are components that I use in my personal setup. Feel free to use them if you want! But you
can expect breaking changes 😇


<!-- vim-markdown-toc GFM -->

* [What is this?](#what-is-this)
* [Changelog](#changelog)
* [Development](#development)

<!-- vim-markdown-toc -->

## What is this?

These are components that I find useful after running [Home
Assistant](https://www.home-assistant.io/) for a couple of years. Most of these were implemented
using [Node-RED](https://nodered.org/) originally, but maintaining those flows, on multiple
instances started to become a pain. Rewriting them as custom components allows me to write
tests, keep things compatible with the latest HA versions and keep multiple HA instances up to
date.

## Changelog

When updating, be sure to look at the [CHANGELOG](/CHANGELOG.md)!

## Development

If you want to run this locally, the `Makefile` is your best friend:

```console
$ make
Makefile targets:
  ci            Run all CI steps
  test          Run tests with coverage
  tox           Run tests on different HA versions
  tox-env       Run tests on specific HA versions
  lint          Run all linters
  lint-ruff     Lint with ruff
  lint-mypy     Lint with mypy
  d-up          Docker compose reboot and tail logs
  d-stop        Docker compose stop
  clean         Clean up caches and venv
  help          Show this help
```
