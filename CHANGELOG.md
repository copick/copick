# Changelog

## [1.11.0](https://github.com/copick/copick/compare/copick-v1.10.0...copick-v1.11.0) (2025-07-22)


### ✨ Features

* Allow custom metadata on pickable objects ([#117](https://github.com/copick/copick/issues/117)) ([0f4cd98](https://github.com/copick/copick/commit/0f4cd9871d3c68db6858601451d595059cd6dc14))


### 🐞 Bug Fixes

* Minor docs fixes. ([#115](https://github.com/copick/copick/issues/115)) ([91f92b8](https://github.com/copick/copick/commit/91f92b83cf36112ef31b335b37b2eea783659abe))

## [1.10.0](https://github.com/copick/copick/compare/copick-v1.9.0...copick-v1.10.0) (2025-07-21)


### ✨ Features

* Add sync command and CLI ([#113](https://github.com/copick/copick/issues/113)) ([ea28cd7](https://github.com/copick/copick/commit/ea28cd7481d526da8686498c81424009b6cfbc82))

## [1.9.0](https://github.com/copick/copick/compare/copick-v1.8.2...copick-v1.9.0) (2025-07-17)


### ✨ Features

* Add an option allowing extracting run names from filenames ([#111](https://github.com/copick/copick/issues/111)) ([3293545](https://github.com/copick/copick/commit/32935452b46f28cc4f046866d84c5810f359b87b))

## [1.8.2](https://github.com/copick/copick/compare/copick-v1.8.1...copick-v1.8.2) (2025-07-16)


### 🐞 Bug Fixes

* Fix overwrite option on CLI ([#109](https://github.com/copick/copick/issues/109)) ([8232aaf](https://github.com/copick/copick/commit/8232aaf983ad32a0c0c6198cd121e7cd313febb3))

## [1.8.1](https://github.com/copick/copick/compare/copick-v1.8.0...copick-v1.8.1) (2025-07-16)


### 🐞 Bug Fixes

* Make sshfs a core dependency and update docs. ([#107](https://github.com/copick/copick/issues/107)) ([3e5645d](https://github.com/copick/copick/commit/3e5645d35b1db732d1f39e2d1177de674c772be3))

## [1.8.0](https://github.com/copick/copick/compare/copick-v1.7.0...copick-v1.8.0) (2025-07-16)


### ✨ Features

* More CLI groups exposed for entry points from other packages. ([#103](https://github.com/copick/copick/issues/103)) ([f99bb3f](https://github.com/copick/copick/commit/f99bb3f3fa97b8f3b30d4fa54f58bc29f9cd5d64))

## [1.7.0](https://github.com/copick/copick/compare/copick-v1.6.1...copick-v1.7.0) (2025-07-16)


### ✨ Features

* Add ability to add objects. ([#101](https://github.com/copick/copick/issues/101)) ([ee19667](https://github.com/copick/copick/commit/ee196679fc9a198e166a5e8a9baf64882e216a5f))


### 🐞 Bug Fixes

* remove requirement for providing objects when generating a local config project ([#99](https://github.com/copick/copick/issues/99)) ([7a0045d](https://github.com/copick/copick/commit/7a0045d61a42d59e8f6502b4c76f360c7f313bf6))
* Store OME metadata correctly. ([#105](https://github.com/copick/copick/issues/105)) ([144457b](https://github.com/copick/copick/commit/144457bc2041e17b24a48b5bae42ac7e6ae3a190))


### ⚡️ Performance Improvements

* Add parallel processing support for tomogram and segmentation import ([#102](https://github.com/copick/copick/issues/102)) ([944f77c](https://github.com/copick/copick/commit/944f77c359b47c273e3dc59a5376f353b9997ebe))
* Optimize imports to make importing copick quicker and keep CLI snappy ([#104](https://github.com/copick/copick/issues/104)) ([e115d78](https://github.com/copick/copick/commit/e115d781992bd65a3dc06640d17317c2b0d1eeb9))

## [1.6.1](https://github.com/copick/copick/compare/copick-v1.6.0...copick-v1.6.1) (2025-07-08)


### 🐞 Bug Fixes

* bump actions/checkout from 3 to 4 ([#96](https://github.com/copick/copick/issues/96)) ([8f43b4a](https://github.com/copick/copick/commit/8f43b4a29841637d4be4f8be9a435b8d9418cd67))
* bump actions/setup-python from 4 to 5 ([#95](https://github.com/copick/copick/issues/95)) ([08cae6c](https://github.com/copick/copick/commit/08cae6c06cd7f73dc012ec3e32670507916526da))
* bump asdf-vm/actions from 3 to 4 ([#97](https://github.com/copick/copick/issues/97)) ([422969e](https://github.com/copick/copick/commit/422969eb4427145cc11a140450cb58699f0df29c))

## [1.6.0](https://github.com/copick/copick/compare/copick-v1.5.0...copick-v1.6.0) (2025-07-08)


### ✨ Features

* Improved CLI setup. ([#94](https://github.com/copick/copick/issues/94)) ([cce061a](https://github.com/copick/copick/commit/cce061af908a03fe3e76fd9ee817afc63ade9289))


### 🐞 Bug Fixes

* Bump chanzuckerberg/github-actions from 1.5.0 to 6.4.0 ([#91](https://github.com/copick/copick/issues/91)) ([2e225d9](https://github.com/copick/copick/commit/2e225d9bee80d045d38751e69e4a323e020af899))


### 📝 Documentation

* improve setup docs  ([#93](https://github.com/copick/copick/issues/93)) ([4644a2f](https://github.com/copick/copick/commit/4644a2f3cdb9f29b2adbef3ee2afee66f4f99c6c))

## [1.5.0](https://github.com/copick/copick/compare/copick-v1.4.0...copick-v1.5.0) (2025-06-21)


### ✨ Features

* Generate Config Files for the Dataportal Through CLI ([#77](https://github.com/copick/copick/issues/77)) ([7b1daaf](https://github.com/copick/copick/commit/7b1daafc10c8a39e839e577786cf5619902d9246))

## [1.4.0](https://github.com/copick/copick/compare/copick-v1.3.0...copick-v1.4.0) (2025-06-21)


### ✨ Features

* Add utility to generate empty-picks for a new copick project ([#79](https://github.com/copick/copick/issues/79)) ([d5d5030](https://github.com/copick/copick/commit/d5d50307b82bf230b9dfbe81a09b7c9416b63a79))

## [1.3.0](https://github.com/copick/copick/compare/copick-v1.2.0...copick-v1.3.0) (2025-06-21)


### ✨ Features

* Allow querying copick tomograms with portal metadata ([b1920f6](https://github.com/copick/copick/commit/b1920f60e93e542be75d07ec43fbed2c09e71983))
* Switch to uv for test workflows and activate codecov ([#80](https://github.com/copick/copick/issues/80)) ([1eb0212](https://github.com/copick/copick/commit/1eb02128b153b154cfbab18c11537333544dd208))


### 🐞 Bug Fixes

* changes for smbfs caused duplications with localfs ([fa94e38](https://github.com/copick/copick/commit/fa94e38aefedce1d96bf5e5c294639cadc03ea7a))
* Fix point initialization and loading ([#81](https://github.com/copick/copick/issues/81)) ([7205c24](https://github.com/copick/copick/commit/7205c24516b7699f84a5a96e3e55050a6adf50d6))
* Make cryoET data portal implementation compatible with python 3.9 ([f87688b](https://github.com/copick/copick/commit/f87688b07c92504040d92b997fdaa65dd054676a))
* Reading annotations with shape type "Point" from portal and portal project autogen. ([0a13aec](https://github.com/copick/copick/commit/0a13aeccb2ea5fef827efb5fbb2395eb43e4dfff))


### 🧹 Miscellaneous Chores

* Add conventional commit action. ([#86](https://github.com/copick/copick/issues/86)) ([9f8708f](https://github.com/copick/copick/commit/9f8708f4a7f0ad8b83828b3162bbb24bc40f6293))
* Bump astral-sh/setup-uv from 5 to 6 ([#85](https://github.com/copick/copick/issues/85)) ([503415d](https://github.com/copick/copick/commit/503415d344571ba6e3b022736f6edccb7c58c193))
* Bump peaceiris/actions-gh-pages from 3 to 4 ([#83](https://github.com/copick/copick/issues/83)) ([d5b286a](https://github.com/copick/copick/commit/d5b286ac7061d11ca212bc57efdbbb6338e35d78))
* Update README.md ([#88](https://github.com/copick/copick/issues/88)) ([38f1e79](https://github.com/copick/copick/commit/38f1e7971cafd864c85f198d3a9ad8c7d6492e29))
