var path = require('path')
var webpack = require('webpack')

module.exports = {
  mode: 'development',
  entry: {
    app: ['webpack/hot/dev-server', './Client/entry.jsx']
  },
  output: {
    path: path.join(__dirname, 'public'),
    filename: 'bundle.js',
    publicPath: 'http://localhost:5000/public/'
  },
  devServer: {
    contentBase: './',
    publicPath: 'http://localhost:5000/public/'
  },
  module: {
    rules: [
      // js
      {
        test: /\.jsx?$/,
        loader: 'babel-loader',
        include: [path.join(__dirname, 'Client')]
      },
      // CSS
      {
        test: /\.styl$/,
        include: [path.join(__dirname, 'Client')],
        use: ['style-loader', 'css-loader', 'stylus-loader']
      },
      {
        test: /\.less$/,
        include: [path.join(__dirname, 'Client')],
        use: [
          'style-loader',
          'css-loader',
          'less-loader',
          {
            loader: 'postcss-loader',
            options: {
              plugins: () => {
                return [autoprefixer]
              }
            }
          }
        ]
      },
      {
        test: /\.css$/,
        use: [
          'style-loader',
          'css-loader',
          {
            loader: 'postcss-loader',
            options: {
              plugins: () => {
                return [autoprefixer]
              }
            }
          }
        ]
      },
      // Images
      {
        test: /\.(jpe?g|png|gif|svg)$/i,
        include: [path.join(__dirname, 'Client')],
        use: [
          {
            loader: 'file-loader',
            options: {
              hash: 'sha512',
              digest: 'hex',
              name: '[hash].[ext]'
            }
          },
          {
            loader: 'image-webpack-loader',
            options: {
              query: {
                gifsicle: {
                  interlaced: false
                },
                optipng: {
                  optimizationLevel: 7
                }
              }
            }
          }
        ]
      },
      // Audio
      {
        test: /\.mp3$/,
        include: [path.join(__dirname, 'Client/audio')],
        loader: 'file-loader'
      },
      // Fonts
      {
        test: /\.woff(2)?(\?v=[0-9]\.[0-9]\.[0-9])?$/,
        loader: 'url-loader',
        options: {
          limit: 100000,
          mimetype: 'application/font-woff'
        }
      },
      {
        test: /\.(ttf|eot|svg)(\?v=[0-9]\.[0-9]\.[0-9])?$/,
        loader: 'file-loader'
      }
    ]
  },
  plugins: [
    new webpack.HotModuleReplacementPlugin(),
    new webpack.IgnorePlugin(new RegExp('^(fs|ipc)$'))
  ]
}
