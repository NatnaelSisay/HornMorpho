"""
This file is part of L3Morpho.

    L3Morpho is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    L3Morpho is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with L3Morpho.  If not, see <http://www.gnu.org/licenses/>.
--------------------------------------------------------------------
Author: Michael Gasser <gasser@indiana.edu>

Morphological processing.
Morphology and POSMorphology objects.
Analysis, generation.
Loading, composing, saving FSTs.

-- 2011-07-18
   Morphology responsible for how to pretty print analyses.
-- 2011-07-24
   gen() presents a menu of options for user to change in FS.
"""

import sys
from .fst import *

## Default punctuation characters
PUNCTUATION = r'[“‘”’–—…¿¡•:;/\,<>?.!%$()[]{}|#@&*-_+="\'`^~]'
## Default alphabetic characters
CHARACTERS = r'[a-zA-Z]'

class Morphology(dict):
    """A dict of POSMorphology dicts, one for each POS class that has bound morphology."""

    version = 3.0
    complex = 0
    simple = 1

    def __init__(self, fsh=None, pos_morphs=[],
                 punctuation='', characters=''):
#                 feat_abbrevs=None,
#                 fv_abbrevs=None):
# excl_feats=None):
# , lex_feats=None):
        dict.__init__(self)
        if fsh:
            self.set_fsh(*fsh)
        else:
            self.fsh = None
        self.pos = []
        for pos_morph in pos_morphs:
            if not isinstance(pos_morph, tuple):
                pos_morph = (pos_morph,)
            label = pos_morph[0]
            posmorph = POSMorphology(*pos_morph)
            self[label] = posmorph
            posmorph.morphology = self
            self.pos.append(label)
        # Function that simplifies orthography
        self.simplify = None
        # Function that converts phonological to orthographic representation
        self.orthographize = None
        # Function that returns trivially analyzable forms
        self.triv_anal = None
        # Function that converts (POS, root, citation, FS) to a string
        self.anal2string = None
        # Pair of lists of unanalyzable words: (complex, simple)
        self.words = [[], []]
        self.words_phon = [{}, {}]
        self.seg_units = []
        self.language = None
        # Dictionary of preanalyzed words (varying POS)
        self.analyzed = {}
        self.analyzed_phon = {}
        # Dict of root frequencies
        self.root_freqs = None
        # Dict of grammatical feature frequencies
        self.feat_freqs = None
        # FST for making forms phonetic
        self.phon_fst = None
        self.directory = ''
        self.punctuation = punctuation or PUNCTUATION
        self.characters = characters or CHARACTERS
        # Make punctuation regular expression objects and substitution string
        self.init_punc(self.characters, self.punctuation)
#        # Dict of feature names expanded to more readable strings
#        self.feat_abbrevs = feat_abbrevs or {}
        # List of feat-val pair list and abbreviations
#        self.fv_abbrevs = fv_abbrevs or []

    def get_cas_dir(self):
        return os.path.join(self.directory, 'cas')

    def get_lex_dir(self):
        return os.path.join(self.directory, 'lex')

    def get_fst_dir(self):
        return os.path.join(self.directory, 'fst')

    def get_stat_dir(self):
        return os.path.join(self.directory, 'stat')

    def expand_abbrev(self, abbrev):
        return self.feat_abbrevs.get(abbrev, abbrev)

    def init_punc(self, chars, punc):
        '''Make punctuation regular expression objects and substitution string.'''
        self.punc_after_re = re.compile(r'(' + chars + r')(' + punc + r')', re.U)
        self.punc_before_re = re.compile(r'(' + punc + r')(' + chars + r')', re.U)
        self.punc_sub = r'\1 \2'

    def sep_punc(self, text):
        """Separate punctuation from words."""
        text = self.punc_after_re.sub(self.punc_sub, text)
        text = self.punc_before_re.sub(self.punc_sub, text)
        return text

    def is_word(self, word, simple=False, ortho=True):
        """Is word an unanalyzable word?"""
        if ortho and word in self.punctuation:
            return word
        if ortho and not self.words:
            return None
        if not ortho and not self.words_phon:
            return None
        if ortho:
            word_rec = self.words[Morphology.simple if simple else Morphology.complex]
            return word in word_rec and word
        else:
            word_rec = self.words_phon[Morphology.simple if simple else Morphology.complex]
            return word_rec.get(word, False)

    def feat_name(self, values):
        if any(values):
            return '+'.join(values)
        else:
            return ''

    def rv_name(self, root, value):
        if value:
            return root + '+' + value
        else:
            return root

    def root_fv(self, root, anal):
        root_feats = self.language.stat_root_feats
        value = self.feat_name([anal.get(f, '') for f in root_feats])
        return self.rv_name(root, value)

    def get_fv(self, feats, anal):
        a = anal
        for f in feats:
            if f in a:
                a = a.get(f)
            else:
                return 'nothing'
        return a
        
    def get_root_freq(self, root, anal):
        rv = self.root_fv(root, anal)
        if self.root_freqs:
            return self.root_freqs.get(rv, 0)
        return 100

    def get_feat_freq(self, anal):
        freq = 1.0
        if self.feat_freqs:
            for f in self.language.stat_feats:
                v = self.get_fv(f, anal)
                if v != 'nothing':
                    feat_name = '+'.join(f)
                    freq0 = self.feat_freqs.get(feat_name, {}).get(v, 1.0)
                    freq *= freq0
        return freq

    def set_root_freqs(self):
        filename = 'root_freqs.dct'
        path = os.path.join(self.get_stat_dir(), filename)
        try:
            with open(path, encoding='utf-8') as roots:
                self.root_freqs = eval(roots.read())
        except IOError:
            pass
#            print('No root frequency file {} found'.format(path))

    def set_feat_freqs(self):
        filename = 'feat_freqs.dct'
        path = os.path.join(self.get_stat_dir(), filename)
        try:
            with open(path, encoding='utf-8') as feats:
                self.feat_freqs = eval(feats.read())
        except IOError:
            pass
#            print('No file frequency file {} found'.format(path))

    def set_words(self, filename='words.lex', ortho=True, simplify=False):
        '''Set the list/dict of unanalyzed words, reading them in from a file, one per line.'''
        if not ortho:
            filename = 'words_phon.lex'
        path = os.path.join(self.get_lex_dir(), filename)
#        path = os.path.join(self.directory, filename)
        position = Morphology.simple if simplify else Morphology.complex
        if os.path.exists(path):
            file = open(path, encoding='utf8')
            if ortho:
                # Read in the words as a list
                self.words[position] = [w.strip() for w in file]
            else:
                # Read in ortho:phon pairs as a dict
                self.words_phon[position] = dict([w.split() for w in file])
            file.close()
        else:
            self.words = []
            self.words_phon = []

    def get_analyzed(self, word):
        '''Get the pre-analyzed FS for word.'''
        return self.analyzed.get(word)

    def set_analyzed(self, filename='analyzed.lex', ortho=True, verbose=False):
        '''Set the dict of analyzed words, reading them in from a file, one per line.'''
        if not ortho:
            filename = 'analyzed_phon.lex'
        path = os.path.join(self.get_lex_dir(), filename)
#        path = os.path.join(self.directory, filename)
        if os.path.exists(path):
            file = open(path, encoding='utf8')
            if verbose:
                print('Storing pre-analyzed forms')
            if ortho:
                for line in file:
                    # Word and FS separated by two spaces
                    word, anal = line.split('  ')
                    fs = FSSet.parse(anal.strip())
                    self.analyzed[word] = fs
            else:
                for line in file:
                    # Word and FS separated by two spaces
                    word, phon, anal = line.split('  ')
                    fs = FSSet.parse(anal.strip())
                    self.analyzed_phon[word] = (phon, fs)
            file.close()

    def set_fsh(self, *label_fs):
        """Set the Feature Structure Hierarchy for this language's morphology."""
        self.fsh = FSHier()
        self.fsh.parse(label_fs)

    def trivial_anal(self, form):
        """Attempt to trivially analyze form."""
        return self.triv_anal and self.triv_anal(form)

    def anal(self, form, pos, to_dict=True, preproc=False, guess=False, phon=False, segment=False,
             trace=False, tracefeat=''):
        return self[pos].anal(form, to_dict=to_dict, preproc=preproc, guess=guess, phon=phon, segment=segment,
                              trace=trace, tracefeat=tracefeat)

    def gen(self, form, features, pos, from_dict=True, postproc=False, guess=False, phon=False, segment=False,
            trace=False):
        return self[pos].gen(form, features, from_dict=from_dict, postproc=postproc,
                             guess=guess, phon=phon, segment=segment, trace=trace)

    def load_fst(self, label, generate=False, create_fst=True, save=False, verbose=False):
        """Load an FST that is not associated with a particular POS."""
        path = os.path.join(self.get_cas_dir(), label + '.cas')
#        path = os.path.join(self.directory, label + '.cas')
        casc = fst = None
        if verbose: print('Looking for cascade at', path)
        if os.path.exists(path):
            # Load each of the FSTs in the cascade and compose them
            if verbose: print('Loading cascade ...')
            casc = FSTCascade.load(path, seg_units=self.seg_units, language=self.language,
                                   create_networks=True)
            # create_fst is False in case we just want to load the individuals fsts.
            if create_fst:
                if verbose:
                    print("Composing FST")
                fst = casc.compose(backwards=False, trace=verbose, relabel=True)
                if generate:
                    fst = fst.inverted()
                if save:
                    FST.write(fst, filename=os.path.join(self.get_fst_dir(), label + '.fst'))
                return fst
            return casc

    def restore_fst(self, label, create_networks=False):
        '''Return the FST with label.'''
        cas_path = os.path.join(self.get_cas_dir(), label + '.cas')
        cascade = None
        if os.path.exists(cas_path):
            cascade = FSTCascade.load(cas_path,
                                      language=self.language,
                                      seg_units=self.seg_units,
                                      create_networks=create_networks,
                                      verbose=False)
        if cascade != None:
#            print('Restoring FST', label)
            # Look for the full, explicit FST
            fst_file = label + '.fst'
            fst_path = os.path.join(self.get_fst_dir(), fst_file)
            if os.path.exists(fst_path):
                return FST.restore_parse(self.get_fst_dir(), fst_file, cascade=cascade,
                                         weighting=UNIFICATION_SR,
                                         seg_units=self.seg_units,
                                         create_weights=True)

    def load_phon_fst(self, save=True, verbose=True):
        """Load the phon FST if there is one."""
        cascade = FSTCascade.load(os.path.join(self.get_cas_dir(), 'phon.cas'),
                                  language=self.language,
                                  seg_units=self.seg_units, create_networks=True,
                                  verbose=verbose)
        if cascade:
            fst = cascade.compose(backwards=False, trace=verbose)
            if fst:
                fst = fst.inverted()
                if save:
                    FST.write(fst, filename=os.path.join(self.get_fst_dir(), 'phon.fst'))
                    self.phon_fst = fst
                return fst

    def ortho2phon(self, word):
        '''Attempt to convert a word to its phonetic form. (Assumes word is already romanized.)'''
        if word.isdigit():
            # word consists only of numbers
            return [word]
        if self.words_phon:
            words = self.words_phon[Morphology.complex]
            if not isinstance(words, dict):
                print('Words dict is not loaded!')
                return
            phon = words.get(word, '')
            if phon:
                return [phon]
        elif word in self.analyzed_phon:
            form, fss = self.analyzed_phon[word]
            return [form]

    def phonetic(self, form):
        '''Make a form phonetic, calling the phon FST on it.'''
        fst = self.phon_fst
        if fst:
            phoneticized = fst.transduce(form, seg_units=self.seg_units)
            if phoneticized:
                return phoneticized[0][0]
        return form

class POSMorphology:
    """Lists of MorphCats and GramCats, anal and gen FSTs for a particular POS class."""

    # Indices for different FSTs in self.fsts
    # Top level
    anal_i = 0
    gen_i = 1
    # Indices within sublists
    guess_i = 1
    # Not currently used; save for some future purpose?
    simp_i = 2
    phon_i = 3
    guessphon_i = 4
    seg_i = 5

    def __init__(self, pos, feat_list=None, lex_feats=None,
                 excl_feats=None, feat_abbrevs=None,
                 fv_abbrevs=None, fv_dependencies=None, fv_priority=None):
        # A string representing part of speech
        self.pos = pos
        # Weight constraint on FST arcs
        self.wc = None if pos == 'all' else FSSet('[pos=' + pos + ']')
        # The string used as type in FSs
        self.type = '%' + pos
#        # List of changeable features (not used for AfSem)
#        self.changefeats = changefeats
        # FSTs: [[anal, anal0, None, anal_P, anal0_P, anal_Seg],
        #        [gen, gen0, None, gen_P, gen0_P, (gen_Seg)]]
        self.fsts = [[None, None, None, None, None, None], [None, None, None, None, None, None]]
        # FST cascade
        self.casc = None
        self.casc_inv = None
        self.morphology = None
        self.language = None
        # Default FS for generation
        self.defaultFS = ''
        # Default FS for citation
        self.citationFS = ''
        # Dictionary of FS implications
        self.FS_implic = {}
        ## Functions
        self.anal_to_dict = lambda root, fs: {'root': root}
        self.dict_to_anal = lambda root, dct: ['', FSSet('[]')]
        # Generate citation form
        self.citation = None
        # Analysis to string
        self.anal2string = None
        # Postprocess (roots might be treated specially)
        self.postprocess = None
        # Pair of dicts of common and irregular analyzed words: (complex, simple)
        self.analyzed = ({}, {})
        self.analyzed_phon = ({}, {})
        # Dict of possible grammatical features and their values
        self.features = {}
        # List of morpheme labels
        self.morphs = []
        # List of most "interesting" features
        self.sig_features = []
        # Defective roots
        self.defective = []
        # List of features and possible values
        self.feat_list = feat_list or []
        # List of lexical features: excluded from default for generation
        self.lex_feats = lex_feats or []
        # List of features to exclude from printed analysis output
        self.excl_feats = excl_feats or []
        # List of abbreviations for features
        self.feat_abbrevs = feat_abbrevs or []
        # List of abbreviations for feat-value combinations
        self.fv_abbrevs = fv_abbrevs or []
        # List of feature-value dependencies
        self.fv_dependencies = fv_dependencies or {}
        # List of feature-value pairs that have priority over others in displaying
        self.fv_priority = fv_priority or []

    def __str__(self):
        '''Print name.'''
        return self.pos + '_morphology'

    def __repr__(self):
        '''Print name.'''
        return self.pos + '_morphology'

    def get_fst(self, generate=False, guess=False, simplified=False, phon=False, segment=False):
        """The FST satisfying the parameters."""
        analgen = self.fsts[self.gen_i if generate else self.anal_i]
        if guess:
            if phon:
                fst = analgen[self.guessphon_i]
            else:
                fst = analgen[self.guess_i]
        elif simplified:
            fst = analgen[self.simp_i]
        elif phon:
            fst = analgen[self.phon_i]
        elif segment:
            fst = analgen[self.seg_i]
        else:
            fst = analgen[0] or analgen[self.guess_i] or analgen[self.simp_i]
        return fst

    def set_fst(self, fst, generate=False, guess=False, simplified=False,
                phon=False, segment=False):
        """Assign the FST satisfying the parameters."""
        index2 = 0
        if simplified:
            index2 = self.simp_i
        elif guess:
            if phon:
                index2 = self.guessphon_i
            else:
                index2 = self.guess_i
        elif phon:
            index2 = self.phon_i
        elif segment:
            index2 = self.seg_i
        self.fsts[self.gen_i if generate else self.anal_i][index2] = fst
        # Also assign the defaultFS if the FST has one
        if fst._defaultFS:
            self.defaultFS = fst._defaultFS.__repr__()
#            print(self, 'assigned default FS', self.defaultFS)

    def fst_name(self, generate=False, guess=False, simplified=False,
                 phon=False, segment=False):
        """Make a name for the FST satisfying the parameters."""
        pos = self.pos
        if guess:
            pos += '0'
            if phon:
                pos += 'P'
        elif simplified:
            pos += '_S'
        elif phon:
            pos += 'P'
        elif segment:
            pos += '+'
        if generate:
            pos += 'G'
        return pos

    def get_analyzed(self, word, simple=False):
        """Stored analysis of word if there is one."""
        if self.analyzed:
            return self.analyzed[Morphology.simple if simple else Morphology.complex].get(word, None)

    def set_analyzed(self, filename='analyzed.lex', ortho=True, simplify=True, verbose=False):
        '''Set the dict of analyzed words, reading them in from a file, one per line.'''
        if not ortho:
            filename = 'analyzed_phon.lex'
        path = os.path.join(self.morphology.get_lex_dir(), self.pos + '_' + filename)
        if os.path.exists(path):
            file = open(path)
            if verbose:
                print('Storing irregular pre-analyzed forms:', self.pos)
            for line in file:
                # For ortho=True, each line is
                # word  root  FSS
                # For ortho=False, each line is
                # word phon root FSS
                split_line = line.partition(' ')
                word = split_line[0]
                if not ortho:
                    split_line = split_line[2].strip().partition(' ')
                    phon = split_line[0]
                split_anal = split_line[2].strip().partition(' ')
                root = split_anal[0]
                fs = split_anal[2]
                if word and fs:
                    if not root:
                        root = word
                    fs = FSSet.parse(fs)
                    if ortho:
                        self.analyzed[Morphology.complex][word] = [root, fs]
                    else:
                        self.analyzed_phon[Morphology.complex][word] = [phon, root, fs]
                    if simplify:
                        word = self.morphology.simplify(word)
                        root = self.morphology.simplify(root)
                        if ortho:
                            self.analyzed[Morphology.simple][word] = [root, fs]
                        else:
                            self.analyzed_phon[Morphology.simple][word] = [phon, root, fs]
            file.close()

    def get_features(self):
        '''Get the dict of grammatical features and values, generating it if {}.'''
        if not self.features:
            fst = self.get_fst()
            if fst:
                self.features = fst.get_features()
        return self.features

    def has_cas(self, generate=False, simplified=False, guess=False,
                phon=False, segment=False):
        """Is there a cascade file for the given FST features?"""
        name = self.fst_name(generate=generate, simplified=simplified,
                             guess=guess, phon=phon, segment=segment)
        path = os.path.join(self.morphology.get_cas_dir(), name + '.cas')
        return os.path.exists(path)

    # This is a mess. Fix it at some point.

    def load_fst(self, compose=False, subcasc=None, generate=False, gen=False,
                 recreate=False, create_fst=True, create_casc=False,
                 create_weights=False, guess=False,
                 simplified=False, phon=False, segment=False,
                 invert=False, compose_backwards=True,
                 relabel=True, verbose=False):
        '''Load FST; if compose is False, search for saved FST in file and use that if it exists.

        If guess is true, create the lexiconless guesser FST.'''
        fst = None
        name = self.fst_name(generate, guess, simplified, phon=phon, segment=segment)
        path = os.path.join(self.morphology.get_cas_dir(), name + '.cas')
        if verbose:
            s1 = 'Attempting to load {0} FST for {1} {2}{3}{4}'
            print(s1.format(('GENERATION' if generate else 'ANALYSIS'),
                            self.language.label, self.pos,
                            (' (GUESSER)' if guess else ''),
                            (' (SEGMENTED)' if segment else '')))
        if not compose and not recreate:
            # Load a composed FST encompassing everything in the cascade
            fst = FST.restore(self.pos, cas_directory=self.morphology.get_cas_dir(),
                              fst_directory=self.morphology.get_fst_dir(),
                              seg_units=self.morphology.seg_units,
                              create_weights=create_weights, generate=generate,
                              empty=guess, phon=phon, segment=segment, simplified=simplified,
                              verbose=verbose)
            if fst:
                self.set_fst(fst, generate, guess, simplified, phon=phon, segment=segment)
                if create_casc:
                    if not self.casc:
                        casc = FSTCascade.load(path,
                                               seg_units=self.morphology.seg_units,
                                               create_networks=True, subcasc=subcasc,
                                               language=self.language,
                                               verbose=verbose)
                        if casc:
                            self.casc = casc
                            self.casc_inv = self.casc.inverted()
#                if verbose: print('... loaded')
        if not self.get_fst(generate, guess, simplified, phon=phon, segment=segment) or recreate:
            # Either there was no composed FST or we're supposed to recreate it anyway, so get
            # the cascade and compose it (well, unless create_fst is False)
#            if verbose: print('Looking for cascade at', path, 'subcasc', subcasc)
            if os.path.exists(path):
                # Load each of the FSTs in the cascade and compose them
                if verbose: print('Recreating...')
                self.casc = FSTCascade.load(path,
                                            seg_units=self.morphology.seg_units,
                                            create_networks=True, subcasc=subcasc,
                                            language=self.language,
                                            verbose=verbose)
                if self.morphology.fsh:
                    self.casc.set_init_weight(FeatStruct('[' + self.type + ']', fsh=self.morphology.fsh))
                self.casc_inv = self.casc.inverted()
                # create_fst is False in case we just want to load the individuals fsts.
                if create_fst:
                    if verbose:
                        print("Composing analysis FST")
                    fst = self.casc.compose(backwards=compose_backwards, trace=verbose, subcasc=subcasc,
                                            relabel=relabel)
                    if invert:
                        fst = fst.inverted()
                    self.set_fst(fst, generate, guess, simplified, phon=phon, segment=segment)
                    self.casc.append(fst)
            elif verbose:
                print('  No cascade exists at', path, end=' ')
                if gen: print()
        if gen:
            if not self.load_fst(compose=False, generate=True, gen=False, create_casc=create_casc,
                                 guess=guess, simplified=simplified, phon=phon, segment=segment,
                                 invert=True, verbose=verbose):
                # Explicit generation FST not found, so invert the analysis FST
                if verbose: print("... inverting analysis FST")
                fst = fst or self.get_fst(False, guess, simplified, phon=phon, segment=segment)
                if fst:
                    self.set_fst(fst.inverted(), True, guess, simplified,
                                 phon=phon, segment=segment)
                    if create_casc:
                        if not self.casc:
                            casc = FSTCascade.load(path,
                                                   seg_units=self.morphology.seg_units,
                                                   create_networks=True, subcasc=subcasc,
                                                   language=self.language,
                                                   verbose=verbose)
                            if casc:
                                self.casc = casc
                                self.casc_inv = self.casc.inverted()
                else:
                    name = self.fst_name(False, guess, simplified, phon=phon, segment=segment)
                    path = os.path.join(self.morphology.get_cas_dir(), name + '.cas')
                    # OK, as a last resort, try again to load the analysis cascade
                    if os.path.exists(path):
                        casc = FSTCascade.load(path,
                                               seg_units=self.morphology.seg_units,
                                               create_networks=True, subcasc=subcasc,
                                               language=self.language,
                                               verbose=verbose)
                        if casc:
                            self.casc = casc
                            self.casc_inv = self.casc.inverted()
        if self.get_fst(generate, guess, simplified, phon=phon, segment=segment):
            # FST found one way or another
            return True

    def load_gen_fst(self, guess=False, simplified=False, phon=False, segment=False, verbose=False):
        '''Create gen_fst(0) by inverting an existing anal_fst(0) or loading and inverting a generation FST.'''
        if not self.get_fst(True, guess, simplified, phon=phon, segment=segment):
            print('LOADING GEN FST FOR', self.language.label, self.pos, ('(guess)' if guess else ''))
            name = self.fst_name(True, guess, simplified, phon=phon, segment=segment)
            # First try to load the explicit generation FST
            gen = self.load_fst(generate=True, guess=guess, simplified=simplified,
                                phon=phon, segment=segment,
                                invert=True)
            if gen:
                self.set_fst(gen, True, guess, simplified, phon=phon, segment=segment)
            else:
                # The corresponding analysis FST
                anal = self.get_fst(False, guess, simplified, phon=phon, segment=segment)
                if anal:
                    self.set_fst(anal.inverted(), True, guess, simplified, phon=phon, segment=segment)
            if self.casc:
                self.casc_inv = self.casc.inverted()
                self.casc_inv.reverse()

    def save_fst(self, generate=False, guess=False, simplified=False,
                 phon=False, segment=False,
                 features=True, defaultFS=True, stringsets=True):
        '''Save FST in a file.'''
        fname = self.fst_name(generate=generate, guess=guess, simplified=simplified,
                              phon=phon, segment=segment)
        extension = '.fst'
        fst = self.get_fst(generate=generate, guess=guess, simplified=simplified,
                           phon=phon, segment=segment)
        directory = self.morphology.directory
        if defaultFS:
            df = self.defaultFS.__repr__()
        else:
            df = ''
        FST.write(fst, filename=os.path.join(self.morphology.get_fst_dir(), fname + extension),
                  defaultFS=df, stringsets=stringsets,
                  features=features, exclude_features=['t', 'm'])

    def unsave_fst(self, fst_file=True):
        '''Get rid of saved FSTs.'''
        if fst_file:
            os.remove(os.path.join(self.morphology.get_fst_dir(), self.pos + '.fst'))

    def anal(self, form, to_dict=False, preproc=False,
             guess=False, simplified=False, phon=False, segment=False,
             timeit=False, trace=False, tracefeat=''):
        """Analyze form."""
        fst = self.get_fst(generate=False, guess=guess, phon=phon, segment=segment)
        if guess:
            if phon:
                fst = self.fsts[self.anal_i][self.guessphon_i]
            elif segment:
                fst = None
            else:
                fst = self.fsts[self.anal_i][self.guess_i]
        elif simplified:
            fst = self.fsts[self.anal_i][self.simp_i]
        elif phon:
            fst = self.fsts[self.anal_i][self.phon_i]
        elif segment:
            fst = self.fsts[self.anal_i][self.seg_i]
        else:
            fst = self.fsts[self.anal_i][0] or self.fsts[self.anal_i][self.guess_i] or self.fsts[self.anal_i][self.simp_i]
        if fst:
            if preproc:
                # For languages with non-roman orthographies
                form = self.language.preprocess(form)
            # If result is same as form and guess is True, reject
            anals = fst.transduce(form, seg_units=self.morphology.seg_units, reject_same=guess,
                                  trace=trace, tracefeat=tracefeat, timeit=timeit)
            if to_dict:
                anals = self.anals_to_dicts(anals)
            return anals
        elif trace:
            print('No analysis FST loaded for', self.pos)

    def gen(self, root, features=None, from_dict=False, postproc=False, update_feats=None,
            guess=False, simplified=False, phon=False, segment=False, fst=None,
            interact=True, timeit=False, trace=False):
        """Generate word from root and features."""
        if interact and self.feat_list:
            # Get user input from menu
            features = self.fv_menu()
        else:
            features = features or self.defaultFS
        if update_feats:
            # Use explicit FS updates
            features = self.update_FS(FeatStruct(features), update_feats)
        if not features:
            return []
        fst = fst or self.get_fst(generate=True, guess=guess, simplified=simplified,
                                  phon=phon, segment=segment)
        if from_dict:
            # Features is a dictionary; it may contain the root if it's not specified
            anal = self.dict_to_anal(root, features)
            root = anal[0]
            features = anal[1]
        else:
            features = FSSet.cast(features)
        if fst:
            gens = fst.transduce(root, features, seg_units=self.morphology.seg_units, trace=trace, timeit=timeit)
            if postproc:
                # For languages with non-roman orthographies
                for gen in gens:
                    # Replace the wordforms with postprocessed versions
                    gen[0] = self.language.postprocess(gen[0])
            return gens
        elif trace:
            print('No generation FST loaded')

    def anals_to_dicts(self, analyses):
        '''Convert list of analyses to list of dicts.'''
        dicts = []
        for anal in analyses:
            root = anal[0]
            for fs in anal[1]:
                dicts.append(self.anal_to_dict(root, fs))
        return dicts

    def anal_to_gram(self, anal, gen_root=None):
        """Convert an analysis into a list of lists of morphs and grams."""
        gram = []
        for a in anal:
            # A single root, possibly multiple fss
            root = gen_root or a[0]
            # FeatStruct set
            for fs in a[1]:
                gram.append((self.fs_to_morphs(root, fs),
                             self.fs_to_feats(root, fs),
                             a[0]))
        return gram

    def postproc(self, analysis):
        '''Postprocess analysis (mutating it) according postproc attribute in Morphology.'''
        if self.postprocess:
            return self.postprocess(analysis)
        else:
            return analysis

    def update_FS(self, fs, features, top=True):
        """Add or modify features (a FS or string) in fs."""
        fs = fs.copy()
        # First make sure features is a FeatStruct
        if isinstance(features, str):
            features = FeatStruct(features)
        for key, value in features.items():
            # Make True any features that are implied by key
            implications = self.FS_implic.get(key, [])
            # All of the implications associated with key
            for implic in implications:
                # Implications that are not represented as lists just mean
                # to make that feature True
                # (Make sure the feature doesn't have an explicit value)
                if not isinstance(implic, list) and not isinstance(implic, tuple) \
                        and implic not in features:
                    fs.update({implic: True})
            # Complex feature in features
            if isinstance(value, FeatStruct):
                # Recursively update value with value in fs for key
                if key not in fs:
                    return []
                value = self.update_FS(fs.get(key), value, top=False)
                # And make True any features that must be True in value
                for implic in implications:
                    if isinstance(implic, list):
                        for imp in implic:
                            # Should we make sure the feature doesn't have an explicit value?
#                            if imp not in value:
                            value.update({imp: True})
            fs.update({key: value})
        # Finally check all of the key, value pairs in self.FS_implic for
        # which the key is a tuple: (feat, value)
        if top:
            for key, implics in self.FS_implic.items():
                if isinstance(key, tuple):
                    # See whether this tuple represents the value of a feature
                    # in features
                    key_values = key[1]
                    # Could be a string or a list of strings; make sure it's a list
                    if not isinstance(key_values, tuple):
                        key_values = (key_values,)
                    if features.get(key[0], 'missing') in key_values:
                        # If so, apply the constraints, as long as they're not
                        # overridden by an explicit value in features
                        for f, v in implics:
                            # If v is a list, then make the value of the listed
                            # item in the list in fs[f] True
                            if isinstance(v, list):
                                if f in features and v[0] in features[f]:
                                    continue
                                fs[f][v[0]] = True
                            # If v is is tuple, then make the value of the item
                            # in the tuple False
                            elif isinstance(v, tuple):
                                if f in features and v[0] in features[f]:
                                    continue
                                fs[f][v[0]] = False
                            elif f not in features:
                                # Otherwise treat f as feature, v as value in fs
                                fs[f] = v
#        print('FS', fs.__repr__())
        return fs

    def ortho2phon(self, form, guess=False, rank=False):
        """Convert orthographic input to phonetic form.
        If rank is True, rank the analyses by the frequency of their roots."""
        output = {}
        analyzed = self.analyzed_phon[Morphology.complex].get(form, None)
        if analyzed:
            word, root, anals = analyzed
            output[word] = [(0, (self.pos, root, None, anal)) for anal in anals]
            return output
        gen_fst = self.get_fst(generate=True, guess=guess, phon=True)
        if not gen_fst:
            return
        analyses = self.anal(form, guess=guess)
        root_count = 0
        if analyses:
            for root, anals in analyses:
                for anal in anals:
                    if rank:
                        # The freq score is the count for the root-feature combination
                        # times the product of the relative frequencies of the grammatical features
                        root_count = self.morphology.get_root_freq(root, anal)
                        freq_count = self.morphology.get_feat_freq(anal)
                        root_count *= freq_count
                    out = self.gen(root, features=anal, phon=True, fst=gen_fst)
                    for o in out:
                        word = o[0]
                        output[word] = output.get(word, []) + [(round(root_count), self.pos, root, None, anal)]
        return output
    
    def anal1(self, input, label='', casc_label='', index=0, load=False):
        """Analyze input in a single sub-FST, given its label or index in the cascade."""
        return self._proc1(input, label=label, casc_label=casc_label, index=index, load=load,
                           anal=True)

    def gen1(self, input, feats=None, fss=None, label='', casc_label='', index=0, load=False):
        """Generate a form for an input and update features or FSS in a single sub-FST,
        given its label or index in the cascade."""
        return self._proc1(input, feats=feats, fss=fss, label=label, casc_label=casc_label,
                           index=index, load=load, anal=False)

    def _proc1(self, input, feats=None, fss='', label='', casc_label='', index=0,
               load=False, anal=True):
        """Process a form and input features or FSS in a single sub-FST, given its label
        or index in the cascade.
        @param  input: input to FST (wordform or root)
        @type   input: string
        @param  feats: features to add to default for generation
        @type   feats: string of bracketed feature-value pairs
        @param  fss:   feature structure set (alternative to feats)
        @type   fss:   FSSet
        @param  label: name of FST
        @type   label: string
        @param  casc_label: name of alternative cascade (without .cas)
        @type   casc_label: string
        @param  index: index of FST in FSTCascade
        @type   index: int
        @param  load:  whether to (re)load the default cascade
        @type   load:  boolean
        @param  anal:  whether to do analysis as opposed to generation
        @type   anal:  boolean
        @return  analyses or wordforms
        @rtype   list: [[string, FSSet]...]
        """
        if casc_label:
            casc = FSTCascade.load(os.path.join(self.morphology.get_cas_dir(), casc_label + '.cas'),
                                   seg_units = self.morphology.seg_units,
                                   language = self.language,
                                   create_networks=True,
#                                   weight_constraint=self.wc,
                                   verbose=True)
        else:
            if load:
                name = self.fst_name(not anal, False, False)
                self.casc = FSTCascade.load(os.path.join(self.morphology.get_cas_dir(), name + '.cas'),
                                            language = self.language,
                                            seg_units = self.morphology.seg_units,
                                            create_networks=True,
#                                            weight_constraint=self.wc,
                                            verbose=True)
            casc = self.casc
        if label:
            # Find the FST with the particular label
            fst = None
            i = 0
            while not fst and i < len(self.casc):
                f = casc[i]
                if f.label == label:
                    fst = f
                i += 1
        else:
            fst = casc[index]
        if not anal and not fss:
            features = FeatStruct(self.defaultFS)
            if feats:
                features = self.update_FS(features, feats)
            fss = FSSet.cast(features)
        print(('Analyzing' if anal else 'Generating'), input, 'with FST', fst.label)
        if not anal:
            fst = fst.inverted()
        return fst.transduce(input, fss, seg_units=self.morphology.seg_units,
                             timeout=20)

    ## Generating default FS from feature-value pairs in Morphology
    
    def make_default_fs(self):
        dct = {}
        lex_feats = self.lex_feats
        for feat, values in self.feat_list:
            if feat in lex_feats:
                continue
            if isinstance(values, list):
                dct2 = {}
                # feat is a complex feature; values is a list of feat-values tuples
                for feat2, values2 in values:
                    if feat2 in lex_feats:
                        continue
                    dct2[feat2] = values2[0]
                fs2 = FeatStruct(dct2)
                dct[feat] = fs2
            else:
                dct[feat] = values[0]
        fs = FeatStruct(dct)
        return fs

    ## Pretty printing analysis

    def pretty_anal(self, anal):
        root = anal[1]
        fs = anal[3]
        # Leave otu the part of speech for now
        s = self.language.T.tformat('{} = <{}>\n',
#                                    ['POS', self.pos, 'root', root],
                                    ['root', root],
                                    self.language.tlanguages)
        s += self.pretty_fs(fs)
        return s

    def print_anal(self, anal, file=sys.stdout):
        '''Print out an analysis.'''
        s = self.pretty_anal(anal)
        print(s, file=file)

    def pretty_fs(self, fs, printit=False, file=sys.stdout):
        '''Print out an FS.'''
        s = ''
        expansions, feats_used = self.expfv(fs)
        for exp in expansions:
            s += '  {}\n'.format(exp)
        if feats_used is not True:
            for feat, val in fs.items():
                if self.excl(feat, val, feats_used):
                    continue
                if isinstance(val, FeatStruct):
                    abbrevs2, feats_used2 = self.expfv(val)
                    fvstring = abbrevs2
                    if feats_used2 is not True:
                        for feat2, val2 in val.items():
                            if self.excl(feat2, val2, feats_used2):
                                continue
                            fvstring.append(self.fval_string(feat2, val2))
                    if fvstring:
                        fvstring = ', '.join(fvstring)
                        s += '  {} = {}\n'.format(self.exab(feat), fvstring)
                else:
                    s += '  {}\n'.format(self.fval_string(feat, val))
        if printit:
            print(s, file=file)
        return s

    def expfv(self, fs):
        '''Find feature value sets that have special names (expansions).'''
        expansions = []
        feats_used = []
        for fvs in self.fv_priority:
            match = True
            for f, v in fvs:
                if f not in fs or fs[f] != v:
                    match = False
                    break
            if match:
                # Found a fv combination with priority; look up its expansion
                # in fv_abbrevs
                expansion = some(lambda x: x[1] if x[0] == fvs else False, self.fv_abbrevs)
                return [expansion], True
        for fvs, exp in self.fv_abbrevs:
            match = True
            if all([(fv[0] in feats_used) for fv in fvs]):
                continue
            for f, v in fvs:
                if f not in fs or fs[f] != v:
                    match = False
                    break
            if match:
                if exp:
                    # The expansion may be empty
                    expansions.append(exp)
                feats_used.extend([fv[0] for fv in fvs])
        return expansions, feats_used

    def excl(self, feat, val, feats_used):
        """Exclude the feature value pair from the printed output."""
        if feat in feats_used:
            return True
        if val is None or val is 0:
            return True
        if feat in self.excl_feats:
            return True
        if (feat, val) in self.excl_feats:
            return True
        return False

    def exab(self, string):
        """Just a short form for expand_abbrev."""
        return self.feat_abbrevs.get(string, string)

    def fval_string(self, feat, val):
        if isinstance(val, bool):
            return '{}{}'.format('+' if val else '-', self.exab(feat))
        else:
            return '{} = {}'.format(self.exab(feat), self.exab(val))

    def make_fv_lists(self):
        """Make lists of features and possible values
        and another corresponding dictionary with names for features and values.
        """
        fvs = []
        fv_names = []
        for feat, values in self.feat_list:
            if feat in self.excl_feats or feat in self.lex_feats:
                continue
            fvs.append((feat, values))
            if isinstance(values, list):
                # Nesting
                value_names = []
                for val in values:
                    value_names.append((self.exab(val[0]), [self.exab(v) for v in val[1]]))
            else:
                value_names = [self.exab(value) for value in values]
            fv_names.append((self.exab(feat), value_names))
        return fvs, fv_names

    def fv_menu(self, fs=None):
        """Display a menu for the user to make changes to FeatStruct fs."""
        # Start with a copy of the default if no FS is specified
        fs = fs or self.defaultFS.copy()
        fvs, fv_names = self.make_fv_lists()
        dmenu = DMenu(fvs, fv_names, self.fv_dependencies)
        changed_fvs = dmenu.top(fs,
                                tdict=self.language.T,
                                langs=self.language.tlanguages,
                                pretty=self.pretty_fs)
        for cfv in changed_fvs:
            dep = self.fv_dependencies.get(cfv)
            if dep:
                feat_path = tuple(dep[:-1])
                feat_value = dep[-1]
                if not fs.__getitem__(feat_path) == feat_value:
                    print('Changing dependent feature', feat_path, 'to value', feat_value)
                    fs.__setitem__(tuple(dep[:-1]), dep[-1])
        return fs

class MorphCat(list):
    """A list of morphs, default first."""

    def __init__(self, label, *morphs):
        list.__init__(self, morphs)
        self.label = label
        self.default = morphs[0] if morphs else '0'

class GramCat(list):
    """A list of grams."""

    def __init__(self, label, *grams):
        list.__init__(self, grams)
        self.label = label
