# Install

`
source venv/bin/activate
git clone https://github.com/coleifer/sqlcipher3
cd sqlcipher3
SQLCIPHER_PATH=$(brew info sqlcipher | awk 'NR==4 {print $1; exit}'); C_INCLUDE_PATH="$SQLCIPHER_PATH"/include LIBRARY_PATH="$SQLCIPHER_PATH"/lib python setup.py build
SQLCIPHER_PATH=$(brew info sqlcipher | awk 'NR==4 {print $1; exit}'); C_INCLUDE_PATH="$SQLCIPHER_PATH"/include LIBRARY_PATH="$SQLCIPHER_PATH"/lib python setup.py install
`

# Description of RB DB

https://pyrekordbox.readthedocs.io/en/stable/formats/db6.html#djmdcue

# TODO

- [ ] Automatically create smart playlists based on a config. I am tired of creating smart playlists from scratch, should be able to start from a copy of an existing one.
- [ ] Round all BPMs
- [ ] Replace bad bitrates
- [ ] Sync file names and metadata. I've updated title/artist for example in RB, which need to be updated in file name (and be re-pointed at location)
- [ ] When adding new songs, autoamtically set song artists and titles. I drag songs I renamed in and metadata doesn't stick

# Things I Could DO

- [ ] Automatically update cue color
- [ ] Switch hot cue to memory cue, vice versa or both
