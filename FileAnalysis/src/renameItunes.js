(() => {
  'use strict';

  var fs = require('fs');
  var tw = require('./common');
  var mm = require('musicmetadata');

  init();

  // Incoming: track # title
  // Outgoing: title
  function init() {
    let currDir = tw.checkOS('transfer');
    let moveDir = tw.checkOS('music');
    let musicCache = [];

    // Cache to check for Duplicates
    fs.readdir(moveDir, (e, files) => {
      fs.readdir(currDir, (e, files) => {
        files.forEach((filename, index) => {
          let originalFilename = `${currDir}${filename}`;

          // var parser = mm(fs.createReadStream('sample.mp3'), function (err, metadata) {
          //   if (err) throw err;
          //   console.log(metadata);
          // });

          // parser.on('data', (chunk) => {
          //     console.log(chunk);
          // });
          filename = filename.slice(3).trim();
          // let Song = tw.newSong(filename, currDir);

          console.log(filename);
          console.log('-----------------------------------');

          fs.rename(originalFilename, `${currDir}${filename}`, (e) => {
            if (e) {
              console.log(e);
            }
          });
        });
      });
    });
  }
})();