# electron_boilerplate
Boiler plate for personal electron apps. This includes react, es6 support, and various other packages I frequently use. It is not a minimal install but could be used as a starting point.

To use:
```
npm install
```

To start dev server:
```
npm start
```
App can now be viewed at http://localhost:5000

To bundle js:
```
npm run build
```
To start electron app (run this while dev server is running for hot reload):
```
npm start-electron
```
to build electron app as executable choose from the following:
```
npm run build-win64
npm run build-win32
npm run build-linux64
npm run build-linux32
npm run build-ios
npm run build-osx
rpm run build-all
```
