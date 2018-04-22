var path = require('path')
var webpack = require('webpack')
var autoprefixer = require('autoprefixer')
var poststylus = require('poststylus')

module.exports = {
  devtool: 'source-map',
  entry: path.join(__dirname, 'Client/entry.jsx'),
  output: {
    path: path.join(__dirname, '/public'),
    filename: 'bundle.js',
    publicPath: 'http://localhost:5000/'
  },
  plugins: [
    new webpack.optimize.OccurenceOrderPlugin(),
    new webpack.DefinePlugin({
      'process.env': {
        'NODE_ENV': '"production"'
      }
    }),
    new webpack.optimize.UglifyJsPlugin({
      compressor: {
        warnings: false
      }
    })
  ],
  module: {
    loaders: [
      // js
      {
        test: /\.jsx?$/,
        loader: 'babel-loader',
        include: path.join(__dirname, 'Client'),
        query: {
          presets: ['react', 'es2015']
        }
      },
      // CSS
      {
        test: /\.styl$/,
        include: path.join(__dirname, 'Client'),
        loader: 'style-loader!css-loader!stylus-loader'
      },
      {
        test: /\.less$/,
        include: path.join(__dirname, 'Client'),
        loader: 'style!css!autoprefixer!less'
      },
      // Images
      {
        test: /\.(jpe?g|png|gif|svg)$/i,
        include: path.join(__dirname, 'Client'),
        loaders: [
          'file?hash=sha512&digest=hex&name=[hash].[ext]',
          'image-webpack?bypassOnDebug&optimizationLevel=7&interlaced=false'
        ]
      },
      // Fonts
      {
        test: /\.woff(2)?(\?v=[0-9]\.[0-9]\.[0-9])?$/,
        loader: 'url-loader?limit=10000&mimetype=application/font-woff'
      },
      {
        test: /\.(ttf|eot|svg)(\?v=[0-9]\.[0-9]\.[0-9])?$/,
        loader: 'file-loader'
      }
    ]
  },
  stylus: {
    use: [
      poststylus('autoprefixer')
    ]
  }
}
