'use strict'
const execSync = require('child_process').execSync

/*
 * Register routes to the functions declared in this controller.
 */
exports.routes = function(app) {
  app.get('/api/example', get)
}

/*
 * @api [get] /example
 * description: This is an example of how to execute a shell command that requires user input. The rAsPI project contains a directory called shell_scripts with a bash scripted called type_something.sh. When executed, it asks the user to type something and waits for input. Once the user types something and preses enter, it prints back what was typed. This endpoing shows how such a script can be executed via the api.
 * responses:
 *   200:
 *     description: A JSON object with property a property called result which contains an array of returned lines.
 *     schema:
 *       type: object
 *       properties:
 *         result:
 *           type: array
 *   400:
 *     description: An error string
 *     schema:
 *       type: object
 *       properties:
 *         error:
 *           type: string
 */
const get = function (request, response) {
  let result
  try {
    result = execSync('./type_something.sh', // Execute the type_something script exactly as you would from the commandline.
      {
        cwd: global.scriptDir, // This is the directory the command needs to be executed from
        input: 'The rAsPI typed this!', // This acts as though it was typed on the command line
        encoding: 'utf-8' // This tells execSync to return the result as a string
      }
    )
  } catch (Error) {
    response.status(400).send({'error': Error.stdError})
  }
  const resultArray = result.split('\n')
  // turn the results of the command into a utf-8 encoded string and return the result
  response.status(200).send({'result': resultArray})
}
