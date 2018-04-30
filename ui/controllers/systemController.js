'use strict'
const execSync = require('child_process').execSync

/*
 * Register routes to the functions declared in this controller.
 */
exports.routes = function(app) {
  app.get('/api/system', get)
  app.post('/api/system', post)
}

/*
 * @api [get] /system
 * description: This endpoint executes an awk script in the shell_scripts directory which parses a file to return the rAsPI version number.
 * responses:
 *   200:
 *     description: JSON object containing rAsPI version
 *     schema:
 *       type: object
 *       properties:
 *         rAsPI_version:
 *           type: string
 *   400:
 *     description: An error string
 *     schema:
 *       type: object
 *       properties:
 *         error:
 *           type: string
 */
const get = function (request, response) {
  // Example of how to execute an awk script. cwd tells the script run from the script directory and
  // encoding turns the results into a string
  // syntax is execSync(command, {object of params}, error callback())
  let rAsPIver
  try {
    rAsPIver = execSync(
      'awk -f rAsPI_version.awk ../package.json',
      {
        cwd: global.scriptDir,
        encoding: 'utf-8'
      }
    )
  } catch (Error) {
    // If there was an error, return status 400 and a json error object
    // Note that the status is optional, your api will work without it but its nice info to return.
    response.status(400).send({'error': Error.stderr})
  }
  // If there was no error, return status 200 and json data object
  response.status(200).send({'rAsPI_version': rAsPIver.trim()})
}

/*
 * @api [post] /system
 * description: This endpoint allows you to post an allowed command (either sysShutdown or reboot) to be executed by the pi.
 * parameters:
 *   - name: command
 *     in: body
 *     schema:
 *       type: object
 *       properties:
 *         type: string
 *         description: Command to execute on the system.
 *         required: true
 * responses:
 *   200:
 *     description: A string indicating the system status.
 *     schema:
 *       type: string
 *   400:
 *     description: An error string
 *     schema:
 *       type: object
 *       properties:
 *         error:
 *           type: string
 */
const post = function (request, response) {
  switch (request.body.command) {
    case 'Shutdown':
      try {
        execSync('sysShutdown -h now')
      } catch (Error) {
        response.status(400).send({'error': Error.stderr})
      }
      response.status(200).send({'response': 'Executing system shutdown.'})
      break
    case 'Reboot':
      try {
        execSync('sysShutdown -r now')
      } catch (Error) {
        response.status(400).send({'error': Error.stderr})
      }
      response.status(200).send({'response': 'Executing system reboot.'})
      break
    default:
      response.status(400).send({error: 'Unsupported command.'})
  }
}
