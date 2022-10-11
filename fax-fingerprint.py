#!/usr/bin/env python3

import sys
import os
import numpy as np
from scipy.io import wavfile
from bitarray import bitarray
from bitarray.util import make_endian
from crccheck.crc import Crc16IbmSdlc

# not sure if this a good integrator function, seems a bit overcomplicated
# could be reworked at some point, but works quite ok for now
def average(array, step, threshold):
  new_array = np.empty(len(array))
  for i in range(0,len(array),step):
    array_value = 0
    if i+step > len(array):
      to = len(array)
    else:
      to = i+step
    for j in range(i, to, 1):
      array_value += array[j]
    #array_value /= step
    for j in range(i, to, 1):
      if array_value > threshold:
        array_value = 1
      elif array_value < threshold*-1:
        array_value = -1
      new_array[j] = array_value
      #print(str(j)+' = '+str(array_value))
  return new_array

def checkBit(byte, bit):
  if byte & (1 << bit):
    return True
  else:
    return False

def demodulate_fsk(wav_file_path):
  sample_rate, data = wavfile.read(wav_file_path)
  # not sure why dividing the sample rate by 1000 leads
  # to the correct multiply and delay value... but it works ;-)
  magic_value = sample_rate // 1000
  delay = magic_value
  average_step = magic_value
  threshold = 0.001

  # this is the actual fsk decoding magic
  # the algorithm is from https://dsp.stackexchange.com/questions/62079/demodulation-of-fsk-signal
  data = np.multiply(data, np.roll(data, delay))
  data = np.add(data, np.roll(data, delay))
  data = average(data, average_step, threshold)

  # convert to unsigned 8bit
  data = np.multiply(127, data)
  data = np.add(127, data)
  data = data.astype(np.uint8)

  bits = bitarray()
  sample_count = len(data)

  start = 0
  last_start = 0

  last_sample_value = 0
  current_sample_value = 0

  bit_pointer = 0
  output_byte = 0

  # iterate over all samples
  for sample_number, sample_value in enumerate(data):

    last_sample_value = current_sample_value
    current_sample_value = sample_value

    # detect change
    if current_sample_value != last_sample_value:
      last_start = start
      start = sample_number

      sample_count = sample_number - last_start

      length = round(sample_count / (sample_rate / 300))
 
      for i in range(length):

        if current_sample_value < 127:
          bits.append(0)
        else:
          bits.append(1)

  print('')
  print(bits.to01())
  print('')
  print('message contains ' + str(len(bits)) + ' bits')
  print('')
  
  return bits

def find_hdlc_blocks(bits):

  # get blocks between flags
  blocks = []

  flag = bitarray('01111110')
  channel_not_active = bitarray('111111111111111')
  offset = 0

  while offset != -1:

    offset = bits.find(flag)

    block = bits[:offset]
    print('found block with ' + str(len(block)) + ' bits', end='')

    # only use block that are 8 bits or bigger
    if len(block) < 8:
      print(' <- too small, ignoring it')

    # block that contain 'channel not active' symbol are most probably invalid
    elif block.find(channel_not_active) != -1:
      print(' <- contains channel_not_active symbol, ignoring it')
    else:
      print()
      blocks.append(block)

    bits = bits[offset+8:]

  return blocks

def printByteInfo(byte, info = None):
  print('{:08b}'.format(byte) + ' 0x{:02x}'.format(byte), end='')
  if info:
    print(' <- ' + info)
  else:
    print()

def decode_t30_block(bits):

  # remove bit stuffing from message
  bitstuffing = bitarray('111110')
  bitstuffing_offset = bits.find(bitstuffing)
  while bitstuffing_offset != -1:
    bit = bits.pop(bitstuffing_offset + 5)
    bitstuffing_offset = bits.find(bitstuffing, bitstuffing_offset + 1)

  # create byte array
  block_bytes = make_endian(bits, 'little').tobytes()

  # blocks smaller than 5 bytes are most probably invalid
  if len(block_bytes) < 5:
    return
  # block not starting with 11111111 are most probably invalid
  if block_bytes[0] != 255:
    return

  # decode and print some infos
  for i in range(len(block_bytes)):

    byte = block_bytes[i]

    # check sum with highest prio
    if i == len(block_bytes) - 2:
        printByteInfo(byte, 'CRC 1/2')

    elif i == len(block_bytes) - 1:
      block_crc = (block_bytes[-1] << 8) + block_bytes[-2];
      calculated_crc = Crc16IbmSdlc.calc(block_bytes[:-2])
      if block_crc != calculated_crc:
        printByteInfo(byte, 'CRC 2/2 - missmatch - transmitted: ' + hex(block_crc) + ' calcluated: ' + hex(calculated_crc))
      else:
        printByteInfo(byte, 'CRC 2/2 - good: ' + hex(calculated_crc))

    # hdlc control block 
    elif i == 1:
      if byte == 0x3:
        printByteInfo(byte, 'not last block of transmission')
      elif byte == 0x13:
        printByteInfo(byte, 'last block of transmission')
      else:
        printByteInfo(byte)

    # message types
    elif i == 2:
      if byte == 0x20:
        printByteInfo(byte, 'NSF - non standard facilities')
      elif byte == 0x40:
        printByteInfo(byte, 'CSI - call subscriber identification')
      elif byte == 0x80:
        printByteInfo(byte, 'DIS - digital identifier signal')
      else:
        printByteInfo(byte)

    # NSF stuff
    elif i == 3 and block_bytes[2] == 0x20:
      # from ITU-T T.35
      info = '(?) country code'
      if byte == 0xad:
        info += ': united states'
      elif byte == 0x00:
        info += ': japan'
      printByteInfo(byte, info)

    elif i == 4 and block_bytes[2] == 0x20:
      info = '(?) terminal provider code'
      printByteInfo(byte, info)

    elif i == 5 and block_bytes[2] == 0x20:
      info = '(?) terminal provider oriented code'
      printByteInfo(byte, info)

    # DIS stuff
    elif i == 3 and block_bytes[2] == 0x80:
      if checkBit(byte, 2):
        printByteInfo(byte, '-----1-- real time internet fax')
      else:
        printByteInfo(byte)

    elif i == 4 and block_bytes[2] == 0x80:
      info = ''
      if checkBit(byte, 1):
        info += '------1- fax operation  '

      if not checkBit(byte, 2) and not checkBit(byte, 3) and not checkBit(byte, 4) and not checkBit(byte, 5):
        info += '--0000-- v.27 fallback  '
      elif not checkBit(byte, 2) and not checkBit(byte, 3) and checkBit(byte, 4) and not checkBit(byte, 5):
        info += '--0010-- v.27  '
      elif checkBit(byte, 2) and not checkBit(byte, 3) and not checkBit(byte, 4) and not checkBit(byte, 5):
        info += '--0001-- v.29  '
      elif checkBit(byte, 2) and checkBit(byte, 3) and not checkBit(byte, 4) and not checkBit(byte, 5):
        info += '--0011-- v.27 and v.29  '
      elif checkBit(byte, 2) and checkBit(byte, 3) and not checkBit(byte, 4) and checkBit(byte, 5):
        info += '--1011-- v.27 and v.29 and v.17  '
      printByteInfo(byte, info)

    elif i == 5 and block_bytes[2] == 0x80:
      info = ''

      if not checkBit(byte, 0) and not checkBit(byte, 1):
        info += '------00 scan line 215mm  '
      elif not checkBit(byte, 0) and checkBit(byte, 1):
        info += '------10 scan line 215mm, 255mm, 303mm  '
      elif checkBit(byte, 0) and not checkBit(byte, 1):
        info += '------01 scan line 215mm and 255mm  '

      if not checkBit(byte, 2) and not checkBit(byte, 3):
        info += '----00-- A4 length  '
      elif not checkBit(byte, 2) and checkBit(byte, 3):
        info += '----10-- unlimited length  '
      elif checkBit(byte, 2) and not checkBit(byte, 3):
        info += '----01-- A4 and B4 length '

      info += '-???---- minimum scanline time  '
      printByteInfo(byte, info)

    elif i == 8 and block_bytes[2] == 0x80:
      info = ''
      if checkBit(byte, 3):
        info += '----1--- inch-based preferred  '
      if checkBit(byte, 4):
        info += '---1---- metric-based preferred  '
      printByteInfo(byte, info)

    elif i == 9 and block_bytes[2] == 0x80:
      info = ''
      if checkBit(byte, 1):
        info += '------1- password  '
      if checkBit(byte, 2):
        info += '-----1-- ready to transmit data file  '
      if checkBit(byte, 4):
        info += '---1---- BFT binary file transfer  '
      if checkBit(byte, 5):
        info += '--1----- DTM document transfer mode  '
      if checkBit(byte, 6):
        info += '-1------ EDI electronic data interchange  '
      printByteInfo(byte, info)

    elif i == 10 and block_bytes[2] == 0x80:
      info = ''
      if checkBit(byte, 0):
        info += '-------1 BTM basic transfer mode  '
      if checkBit(byte, 1):
        info += '------1- ready to transmit character or mixed document  '
      printByteInfo(byte, info)

    elif i == 11 and block_bytes[2] == 0x80:
      info = ''
      if checkBit(byte, 1):
        info += '------1- digital network capability  '
      if checkBit(byte, 3):
        info += '----1--- JPEG coding  '
      if checkBit(byte, 4):
        info += '---1---- full color mode  '
      printByteInfo(byte, info)

    elif i == 12 and block_bytes[2] == 0x80:
      info = ''
      if checkBit(byte, 3):
        info += '----1--- north americal letter (215.9 x 279.4mm)  '
      if checkBit(byte, 4):
        info += '---1---- north americal legal (215.9 x 355.6mm)  '
      printByteInfo(byte, info)

    # print caller id    
    elif i == len(block_bytes) - 3 and block_bytes[2] == 0x40:
      caller_id = ''
      for j in range(i,2,-1):
        caller_id += chr(block_bytes[j])
      printByteInfo(byte, 'Caller ID: "' + caller_id + '"')

    else:
      printByteInfo(byte)

  print()

if len(sys.argv) < 2:
  print('please supply mono channel, float wav file as argument')
  sys.exit(1)

wav_file_path = sys.argv[1]
if not os.path.isfile(wav_file_path):
  print('wav file not found')
  sys.exit(1)

bits = demodulate_fsk(wav_file_path)
blocks = find_hdlc_blocks(bits)
print()
for block in blocks:
  decode_t30_block(block)

