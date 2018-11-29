(() => {
  'use strict';

  // Link to the directory
  var fs = require('fs');
  var tw = require('./common');

  init();

  var originalArr = [];
  var compareArr = [];

  // Format: artist - album - title
  function init() {
    let currDir = tw.checkOS('music'); // No Cross-Drive Support!

    fs.readdir(currDir, (e, files) => {
      originalArr = tw.cacheMusic(files, currDir);

      compareArr = [...originalArr];

      // Check duplicates
      originalArr.forEach((Song, index) => {
        Song.title = tw.removeClip(Song.title);
        if (Song.title && Song.title.includes('Clip')) {
          console.log(`${index} After: ${Song.title}`);
        }
        if (Song.rating === undefined && Song.extension === '.wav') {
          console.log(Song.filename);
        }
        Song = tw.checkDuplicate(Song, compareArr);
      });
    });
  }
})();